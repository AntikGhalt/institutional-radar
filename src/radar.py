"""CLI and orchestration; the data, rendering and delivery contracts live in dedicated modules."""
import argparse, datetime as dt, os
from pathlib import Path
from src.common import ROOT,TZ,SOURCES,SOURCE_MAP,read,load,write,digest,run_date,scheduled_sunday,allowed,allowed_source
from src.validation import validate_collection,validate_review
from src.collection import collect as _collect,collect_one
from src.rendering import render as _render,event_uid,event_lines,ics_bytes
from src.delivery import send as _send,send_test as _send_test,smtp_deliver,build_message,check_production_date
from src.audit import validate_audit
from src.digest import weekly_health
from src.metrics import contributions

def collect(date,demo=False): return _collect(ROOT,date,demo)
def render(raw,review,health=None,audited=False,publish_links=True): return _render(ROOT,raw,review,health,audited,publish_links)
def send(raw,review,out,title,reserve_only=False): return _send(ROOT,raw,review,out,title,reserve_only,deliver=smtp_deliver)
def send_test(raw,review,out,title): return _send_test(raw,review,out,title,deliver=smtp_deliver)
def make_demo_review(raw):
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1)
    return {"schema":1,"mode":"demo","run_date":raw["run_date"],"collection_sha256":digest(raw),"coverage":[{"institution":s["name"],"status":"partial","note":"Fixture sintetica: fonte non consultata."} for s in SOURCES],"events":[{"institution":s["name"],"title":f"Evento sintetico {i+1} (NON REALE)","date":str(start+dt.timedelta(days=i*7)),"url":s["url"],"relevance":"high","certainty":"confirmed","why":"Test di formattazione, non una pubblicazione reale.","evidence":"Dato sintetico."} for i,s in enumerate(SOURCES[:3])]}
def collection_quality(raw):
    parsers=[(s["institution"],s.get("calendar_parser",{}).get("status")) for s in raw["sources"]]
    configured=[(n,v) for n,v in parsers if v and v!="not_configured"]
    generic_errors=[s["institution"] for s in raw["sources"] if s.get("status")=="error"]
    if not configured: return "unknown","Snapshot privo di diagnostica strutturata."
    failed=[n for n,v in configured if v in ("error","partial_candidates")]
    zero=[n for n,v in configured if v=="no_dated_candidates"]
    note=f"{len(configured)} parser specifici; anomalie: {', '.join(failed) or 'nessuna'}; zero date: {', '.join(zero) or 'nessuno'}; errori accesso generico: {', '.join(generic_errors) or 'nessuno'}."
    return ("partial" if failed or generic_errors else "ok"),note

def prepare(date,persist=False):
    directory=ROOT/"data"/str(date)
    try:
        raw=validate_collection(load(directory/"collection.json"),date)
        python_state=("ok",f"{len(raw['sources'])} fonti registrate; {len(raw.get('events',[]))} candidati datati.")
    except FileNotFoundError:
        raw={"schema":1,"mode":"live","run_date":str(date),"sources":[],"events":[]}
        python_state=("missing","Nessuna raccolta disponibile.")
    except (ValueError,KeyError,TypeError,OSError):
        raw={"schema":1,"mode":"live","run_date":str(date),"sources":[],"events":[]}
        python_state=("invalid","Raccolta non leggibile o non valida.")
    review=None; audit_ok=False; original=None; origin=None; audit=None
    if python_state[0]=="ok":
        try: review=validate_review(raw,load(directory/"review.json"))
        except (FileNotFoundError,ValueError,KeyError,TypeError,OSError): pass
    if raw["mode"]=="demo": return raw,review,None,False
    if python_state[0]=="ok":
        try:
            audit=validate_audit(directory,raw,review,load(directory/"audit.json"))
            audit_ok=True; audit_state=("ok",audit["limitations"])
        except FileNotFoundError: audit_state=("missing","Audit indipendente non consegnato.")
        except (ValueError,KeyError,TypeError,OSError): audit_state=("invalid","Audit non valido o non corrispondente alla revisione.")
        from src.handoff import find_review
        review,claude_status,claude_note,original,origin=find_review(raw,validate_review,review,preferred=(audit or {}).get("claude_review_commit") if audit_ok else None)
        claude_state=(claude_status,claude_note)
    else:
        claude_state=("missing","Raccolta necessaria alla revisione assente o non valida.")
        audit_state=("missing","Raccolta necessaria all’audit assente o non valida.")
    quality=collection_quality(raw) if python_state[0]=="ok" else ("unknown","Qualità non valutabile senza raccolta valida.")
    health=weekly_health(ROOT/"data",str(date),{"python":python_state,"parser_quality":quality,"claude":claude_state,"chatgpt":audit_state})
    health["metrics"]=contributions(raw,original,review,audit_ok,origin)
    # A delivered or reserved run's recorded health must not be silently rewritten.
    if persist and not (directory/"delivery.json").exists(): write(directory/"health.json",health)
    return raw,review,health,audit_ok

def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["collect","demo-review","finalize","hash","validate"]); p.add_argument("--date",type=dt.date.fromisoformat,default=(scheduled_sunday(dt.datetime.now(TZ).date()) if os.getenv("RADAR_SCHEDULED")=="true" else run_date())); p.add_argument("--demo",action="store_true"); p.add_argument("--send",action="store_true"); p.add_argument("--reserve",action="store_true"); p.add_argument("--test-email",action="store_true"); p.add_argument("--review-file",type=Path); a=p.parse_args()
    if a.date.weekday()!=6: p.error("Run date must be a Sunday")
    directory=ROOT/"data"/str(a.date)
    if a.command=="collect":
        if (directory/"collection.json").exists():
            existing=load(directory/"collection.json")
            if existing["mode"] != ("demo" if a.demo else "live"): raise ValueError("Existing collection mode differs")
            print("Existing immutable collection retained"); return
        collect(a.date,a.demo); return
    if a.command=="hash": print(digest(load(directory/"collection.json"))); return
    if a.command=="validate":
        raw=validate_collection(load(directory/"collection.json"),a.date)
        review=validate_review(raw,load(a.review_file or directory/"review.json"))
        print(f"Valid review: {len(review['events'])} events"); return
    if a.command=="demo-review":
        raw=load(directory/"collection.json")
        if raw["mode"]!="demo": raise SystemExit("Demo only")
        write(directory/"review.json",make_demo_review(raw)); return
    if sum((a.send,a.reserve,a.test_email))>1: p.error("Choose reserve, send or test-email, not more than one")
    if a.send or a.reserve: check_production_date(a.date,dt.datetime.now(TZ).date())
    if a.send:
        raw={"mode":"live","run_date":str(a.date)}
        if (directory/"collection.json").exists() and load(directory/"collection.json").get("mode")=="demo": raise ValueError("Demo never sent")
        send(raw,None,ROOT/"output"/str(a.date),""); return
    if a.reserve and (directory/"delivery.json").exists() and load(directory/"delivery.json").get("status")=="sent":
        print("Already delivered; no duplicate email."); return
    raw,review,health,audited=prepare(a.date,persist=not a.test_email and (a.reserve or os.getenv("RADAR_SCHEDULED")=="true"))
    out,title=render(raw,review,health,audited,publish_links=a.reserve); print(out)
    if a.test_email: send_test(raw,review,out,title)
    if a.reserve: send(raw,review,out,title,reserve_only=True)
if __name__=="__main__": main()
