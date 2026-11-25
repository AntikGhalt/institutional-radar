"""Institutional Radar: collection, review validation, preview and gated delivery."""
import argparse, concurrent.futures, datetime as dt, hashlib, html, json, os, re, smtplib, ssl, shutil
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from src.calendars import adapter
from src.audit import validate_audit
from src.digest import weekly_health,full_rows,write_csv,health_html,key
from src.calendar_links import calendar_links,individual_ics_url

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Europe/Rome")
SOURCES=json.loads((ROOT/"config/sources.json").read_text(encoding="utf-8"))
SOURCE_MAP={s["name"]:s for s in SOURCES}
TERMS=re.compile(r"calendar|calendario|agenda|event|release|publication|pubblicazion|comunicat|statistic|rapport|report|news|notizi|studi",re.I)
def read(p): return Path(p).read_text(encoding="utf-8")
def load(p): return json.loads(read(p))
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def run_date():
    d=dt.datetime.now(TZ).date()
    return d+dt.timedelta(days=(6-d.weekday())%7)
def allowed(url,domains):
    p=urlsplit(url); h=p.hostname or ""
    return p.scheme=="https" and not p.username and not p.password and p.port in (None,443) and any(h==d or h.endswith("."+d) for d in domains)
def allowed_source(url,s,legacy_demo=False):
    if not allowed(url,s["domains"]): return False
    if legacy_demo: return True
    p=urlsplit(url); h=p.hostname or ""
    if s["name"]=="Eurostat": return h=="ec.europa.eu" and (p.path=="/eurostat" or p.path.startswith("/eurostat/"))
    if s["name"]=="DG EMPL": return h=="employment-social-affairs.ec.europa.eu" or (h=="ec.europa.eu" and (p.path.startswith("/social/") or p.path=="/social"))
    return True
class Links(HTMLParser):
    def __init__(self): super().__init__(); self.href=None; self.parts=[]; self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a": self.href=dict(attrs).get("href"); self.parts=[]
    def handle_data(self,data):
        if self.href: self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.href:
            self.links.append((self.href," ".join(" ".join(self.parts).split()))); self.href=None
def collect_one(s, start=None, end=None):
    result={"institution":s["name"],"entry_url":s["url"],"links":[]}
    try:
        with urlopen(Request(s["url"],headers={"User-Agent":"InstitutionalRadar/0.1 (research calendar pilot)"}),timeout=15) as r:
            if not allowed_source(r.geturl(),s): raise ValueError("Unexpected redirect domain")
            raw=r.read(2_000_000); base=r.geturl(); enc=r.headers.get_content_charset() or "utf-8"
        parser=Links(); parser.feed(raw.decode(enc,errors="replace")); seen=set()
        for href,title in parser.links:
            url=urljoin(base,href).split("#")[0]
            if allowed_source(url,s) and TERMS.search(title+" "+url) and url not in seen:
                seen.add(url); result["links"].append({"title":title[:240],"url":url})
            if len(seen)>=35: break
        result["status"]="candidates_only" if seen else "no_candidates"
    except Exception as e: result.update(status="error",error=type(e).__name__)
    if start is not None:
        try:
            result["dated_candidates"],result["calendar_parser"]=adapter(s,start,end)
        except Exception as e:
            result["dated_candidates"]=[]; result["calendar_parser"]={"status":"error","attempts":[{"error":type(e).__name__}]}
    return result
def collect(date,demo=False):
    if demo: results=[{"institution":s["name"],"entry_url":s["url"],"links":[],"status":"demo_not_fetched"} for s in SOURCES]
    else:
        start=date+dt.timedelta(days=1); end=start+dt.timedelta(days=29)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: results=list(ex.map(lambda s:collect_one(s,start,end),SOURCES))
    raw={"schema":1,"run_date":str(date),"mode":"demo" if demo else "live","created_at":dt.datetime.now(TZ).isoformat(),"sources":results,"events":[e for s in results for e in s.get("dated_candidates",[])]}
    p=ROOT/"data"/str(date)/"collection.json"
    if p.exists(): raise ValueError("Collection exists; do not overwrite")
    write(p,raw); return raw
def validate_review(raw,review):
    if review["schema"]!=1 or review["run_date"]!=raw["run_date"] or review["collection_sha256"]!=digest(raw): raise ValueError("Review does not match collection")
    if review["mode"]!=raw["mode"]: raise ValueError("Mode mismatch")
    if not isinstance(review["events"],list) or not isinstance(review["coverage"],list): raise ValueError("Invalid lists")
    covered=set()
    for c in review["coverage"]:
        name=c["institution"]
        if name not in SOURCE_MAP or name in covered or c["status"] not in ("checked","partial","unavailable") or not isinstance(c["note"],str) or not c["note"].strip(): raise ValueError("Invalid coverage")
        covered.add(name)
    if covered!=set(SOURCE_MAP): raise ValueError("Coverage must account for every source")
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1); end=start+dt.timedelta(days=29); seen=set()
    for e in review["events"]:
        s=SOURCE_MAP[e["institution"]]
        if not all(isinstance(e[k],str) and e[k].strip() for k in ("title","why","evidence","url")): raise ValueError("Missing evidence")
        if not allowed_source(e["url"],s,legacy_demo=raw["mode"]=="demo"): raise ValueError("Invalid primary URL")
        if e["relevance"] not in ("high","medium","calendar_only") or e["certainty"] not in ("confirmed","tentative"): raise ValueError("Invalid classification")
        date=dt.date.fromisoformat(e["date"])
        if not start<=date<=end: raise ValueError("Outside horizon")
        key=(e["institution"],e["date"]," ".join(e["title"].casefold().split()))
        if key in seen: raise ValueError("Duplicate event")
        seen.add(key)
    return review
def make_demo_review(raw):
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1)
    return {"schema":1,"mode":"demo","run_date":raw["run_date"],"collection_sha256":digest(raw),"coverage":[{"institution":s["name"],"status":"partial","note":"Fixture sintetica: fonte non consultata."} for s in SOURCES],"events":[{"institution":s["name"],"title":f"Evento sintetico {i+1} (NON REALE)","date":str(start+dt.timedelta(days=i*7)),"url":s["url"],"relevance":"high","certainty":"confirmed","why":"Test di formattazione, non una pubblicazione reale.","evidence":"Dato sintetico."} for i,s in enumerate(SOURCES[:3])]}
def esc(x): return html.escape(str(x),quote=True)
def ics_escape(x): return str(x).replace("\\","\\\\").replace("\n","\\n").replace(";","\\;").replace(",","\\,").replace("\r","")
def fold(line):
    chunks=[]; buf=""
    for c in line:
        if len((buf+c).encode())>75: chunks.append(buf); buf=" "+c
        else: buf+=c
    return "\r\n".join(chunks+[buf])
def event_uid(e):
    # Stable across weekly overlapping horizons; same release should use the same UID.
    return digest([e["institution"],e["title"]])[:32]

def event_lines(e,stamp):
    d=dt.date.fromisoformat(e["date"])
    return ["BEGIN:VEVENT","UID:"+event_uid(e)+"@institutional-radar","DTSTAMP:"+stamp,"DTSTART;VALUE=DATE:"+d.strftime("%Y%m%d"),"DTEND;VALUE=DATE:"+(d+dt.timedelta(days=1)).strftime("%Y%m%d"),"SUMMARY:"+ics_escape(e["institution"]+" — "+e["title"]),"DESCRIPTION:"+ics_escape(e["why"]+"\n"+e["url"]),"TRANSP:TRANSPARENT","END:VEVENT"]

def ics_bytes(events,stamp):
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Institutional Radar//IT","CALSCALE:GREGORIAN"]
    for e in events: lines+=event_lines(e,stamp)
    lines.append("END:VCALENDAR")
    return ("\r\n".join(map(fold,lines))+"\r\n").encode()

def render(raw,review,health=None,audited=False):
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1)
    events=sorted((e for e in (review or {}).get("events",[]) if e["relevance"]!="calendar_only"),key=lambda e:(e["date"],e["institution"]))
    out=ROOT/"output"/raw["run_date"]; out.mkdir(parents=True,exist_ok=True)
    individual_dir=out/"calendar-events"
    if individual_dir.exists(): shutil.rmtree(individual_dir)
    individual_dir.mkdir()
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    eligible=[e for e in events if raw["mode"]=="live" and audited and e["certainty"]=="confirmed"]
    individual={}
    for e in eligible:
        uid=event_uid(e)
        (individual_dir/(uid+".ics")).write_bytes(ics_bytes([e],stamp))
        individual[key(e)]=individual_ics_url(raw["run_date"],uid)
    rows=full_rows(raw,review,audited,lambda url,name: name in SOURCE_MAP and allowed_source(url,SOURCE_MAP[name],legacy_demo=raw["mode"]=="demo"),individual)
    title=f"Radar istituzionale | {start:%d/%m/%Y} – {start+dt.timedelta(days=29):%d/%m/%Y}"
    warning="DEMO — nessun evento reale." if raw["mode"]=="demo" else ("Nessuna selezione editoriale disponibile. Il calendario allegato contiene soltanto i candidati recuperati." if review is None else "Selezione verificata dall’audit indipendente, nei limiti indicati." if audited else "Selezione disponibile, ma audit indipendente assente: date non ricontrollate dal secondo agente.")
    if health and health["critical"]: title="[CRITICO] "+title
    elif health and health["degraded"]: title="[PARZIALE] "+title
    h=[f'<!doctype html><html lang="it"><meta charset="utf-8"><body style="font-family:Arial,sans-serif;max-width:780px;margin:auto"><h1>{esc(title)}</h1><p><strong>{esc(warning)}</strong></p>']
    if health and health["critical"]: h.append("<p><strong>PROBLEMA CRITICO: almeno una fase è priva di una consegna verificata da due settimane consecutive.</strong></p>")
    if health and health["degraded"]: h.append(health_html(health))
    h.append(f"<p>{len(events)} appuntamenti selezionati · {len(rows)} voci nel calendario completo.</p>")
    if raw["mode"]=="live" and not raw.get("events"): h.append("<p>Attenzione: nessun candidato datato nella raccolta Python; il CSV contiene soltanto gli eventi individuati nella revisione, se disponibile.</p>")
    for low,high,label in [(0,6,"Settimana in arrivo"),(7,20,"Due settimane successive"),(21,29,"Resto dei 30 giorni")]:
        h.append(f"<h2>{label}</h2>")
        group=[e for e in events if low<=(dt.date.fromisoformat(e["date"])-start).days<=high]
        if not group: h.append("<p>Nessun appuntamento selezionato in questa sezione.</p>")
        for e in group:
            extras=""
            if key(e) in individual:
                link=calendar_links(e,verified=True)
                extras=f' · Aggiungi: <a href="{esc(link["outlook"])}">Outlook</a> | <a href="{esc(link["google"])}">Google Calendar</a> | <a href="{esc(individual[key(e)])}">.ics</a>'
            h.append(f'<p><strong>{esc(e["date"])} — {esc(e["institution"])} — {esc(e["title"])}</strong><br>{esc(e["why"])}<br>{"Confermata nella revisione" if e["certainty"]=="confirmed" else "Provvisoria"} · {"Alta" if e["relevance"]=="high" else "Media"} · <a href="{esc(e["url"])}">Fonte ufficiale</a>{extras}</p>')
    if health and not health["degraded"]: h.append(health_html(health))
    h.append("<h2>Copertura e limiti</h2>")
    coverage={c["institution"]:c for c in review["coverage"]} if review else {}
    counts={state:sum(c["status"]==state for c in coverage.values()) for state in ("checked","partial","unavailable")}
    if coverage:
        h.append(f'<p>Fonti verificate: {counts["checked"]}; parziali: {counts["partial"]}; non disponibili: {counts["unavailable"]}. <a href="https://github.com/AntikGhalt/institutional-radar/tree/main/data/{esc(raw["run_date"])}">Dettagli e dati della rilevazione</a>.</p>')
    for s in raw["sources"]:
        c=coverage.get(s["institution"],{})
        if c.get("status")=="checked": continue
        h.append(f'<p style="font-size:13px">{esc(s["institution"])}: Python {esc(s["status"])}; revisione {esc(c.get("status","assente"))}. {esc(c.get("note",s.get("error","")))}</p>')
    h.append(f"<p>CSV: {len(rows)} appuntamenti recuperati, con stato e collegamenti per aggiungere singole voci. I candidati non verificati aprono bozze contrassegnate «Da verificare». L’ICS cumulativo include solo eventi selezionati di alta rilevanza con data confermata e audit valido. I link individuali .ics sono pubblicati con l’invio.</p></body></html>")
    (out/"report.html").write_text("\n".join(h),encoding="utf-8")
    (out/"calendar.ics").write_bytes(ics_bytes([e for e in eligible if e["relevance"]=="high"],stamp))
    write_csv(out/"full-calendar.csv",rows)
    return out,title
def send(raw,review,out,title,reserve_only=False):
    if raw["mode"]!="live": raise ValueError("Synthetic demo must never be sent")
    if os.getenv("ENABLE_EMAIL")!="true": raise ValueError("Sending disabled")
    receipt=ROOT/"data"/raw["run_date"]/"delivery.json"
    token=os.getenv("RADAR_DELIVERY_TOKEN","")
    if not token: raise ValueError("Delivery requires a workflow reservation token")
    if receipt.exists() and load(receipt).get("status")=="sent":
        print("Already delivered; no duplicate email."); return
    names=["report.html","calendar.ics","full-calendar.csv"]+[str(p.relative_to(out)) for p in sorted((out/"calendar-events").glob("*.ics"))]
    files={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names}
    env={k:os.environ.get(k,"") for k in ("SMTP_USER","SMTP_PASSWORD","NOTIFY_TO")}
    if not all(env.values()): raise ValueError("SMTP credentials or recipient not configured")
    if reserve_only:
        if receipt.exists(): raise ValueError("Already reserved or attempted; inspect receipt before retry")
        published=receipt.parent/"calendar-events"
        if published.exists(): raise ValueError("Individual calendar files already published; inspect run")
        shutil.copytree(out/"calendar-events",published)
        write(receipt,{"status":"reserved","token":token,"at":dt.datetime.now(TZ).isoformat(),"files":files,"subject":title}); return
    if not receipt.exists(): raise ValueError("Missing persisted reservation")
    record=load(receipt)
    if record.get("status")!="reserved" or record.get("token")!=token or record.get("files")!=files: raise ValueError("Missing matching persisted reservation")
    for n in names:
        if n.startswith("calendar-events/") and hashlib.sha256((receipt.parent/n).read_bytes()).hexdigest()!=files[n]: raise ValueError("Published event file mismatch")
    msg=EmailMessage(); msg["Subject"]=record["subject"]; msg["From"]=env["SMTP_USER"]; msg["To"]=env["NOTIFY_TO"]
    msg.set_content("Agenda istituzionale: consultare la versione HTML e gli allegati.")
    msg.add_alternative(read(out/"report.html"),subtype="html")
    msg.add_attachment((out/"full-calendar.csv").read_bytes(),maintype="text",subtype="csv",filename="calendario-completo.csv")
    if b"BEGIN:VEVENT" in (out/"calendar.ics").read_bytes():
        msg.add_attachment((out/"calendar.ics").read_bytes(),maintype="text",subtype="calendar",filename="appuntamenti-selezionati.ics")
    write(receipt,{"status":"attempting","at":dt.datetime.now(TZ).isoformat()})
    try:
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST") or "smtp.gmail.com",int(os.getenv("SMTP_PORT") or "465"),context=ssl.create_default_context(),timeout=30) as smtp:
            smtp.login(env["SMTP_USER"],env["SMTP_PASSWORD"])
            if smtp.send_message(msg): raise RuntimeError("Recipient refused")
    except Exception:
        raise RuntimeError("SMTP attempt failed; inspect sender account before retry") from None
    write(receipt,{"status":"sent","at":dt.datetime.now(TZ).isoformat()})

def prepare(date):
    directory=ROOT/"data"/str(date)
    try:
        raw=load(directory/"collection.json")
        if raw["run_date"]!=str(date) or raw["mode"] not in ("live","demo"): raise ValueError("Invalid collection")
        python_state=("ok",f"{len(raw['sources'])} fonti registrate; {len(raw.get('events',[]))} candidati datati.")
    except FileNotFoundError:
        raw={"schema":1,"mode":"live","run_date":str(date),"sources":[],"events":[]}
        python_state=("missing","Nessuna raccolta disponibile.")
    except (ValueError,KeyError,TypeError,OSError):
        raw={"schema":1,"mode":"live","run_date":str(date),"sources":[],"events":[]}
        python_state=("invalid","Raccolta non leggibile o non valida.")
    review=None; audit_ok=False
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
        review,claude_status,claude_note=find_review(raw,validate_review,review)
        claude_state=(claude_status,claude_note)
    else:
        claude_state=("missing","Raccolta necessaria alla revisione assente o non valida.")
        audit_state=("missing","Raccolta necessaria all’audit assente o non valida.")
    health=weekly_health(ROOT/"data",str(date),{"python":python_state,"claude":claude_state,"chatgpt":audit_state})
    # A delivered or reserved run's recorded health must not be silently rewritten.
    if not (directory/"delivery.json").exists(): write(directory/"health.json",health)
    return raw,review,health,audit_ok

def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["collect","demo-review","finalize","hash"]); p.add_argument("--date",type=dt.date.fromisoformat,default=(dt.datetime.now(TZ).date()-dt.timedelta(days=(dt.datetime.now(TZ).date().weekday()+1)%7) if os.getenv("RADAR_SCHEDULED")=="true" else run_date())); p.add_argument("--demo",action="store_true"); p.add_argument("--send",action="store_true"); p.add_argument("--reserve",action="store_true"); a=p.parse_args()
    if a.date.weekday()!=6: p.error("Run date must be a Sunday")
    directory=ROOT/"data"/str(a.date)
    if a.command=="collect":
        if (directory/"collection.json").exists():
            existing=load(directory/"collection.json")
            if existing["mode"] != ("demo" if a.demo else "live"): raise ValueError("Existing collection mode differs")
            print("Existing immutable collection retained"); return
        collect(a.date,a.demo); return
    if a.command=="hash": print(digest(load(directory/"collection.json"))); return
    if a.command=="demo-review":
        raw=load(directory/"collection.json")
        if raw["mode"]!="demo": raise SystemExit("Demo only")
        write(directory/"review.json",make_demo_review(raw)); return
    if a.send and a.reserve: p.error("Choose reserve or send, not both")
    if a.send:
        raw={"mode":"live","run_date":str(a.date)}
        if (directory/"collection.json").exists() and load(directory/"collection.json").get("mode")=="demo": raise ValueError("Demo never sent")
        send(raw,None,ROOT/"output"/str(a.date),""); return
    raw,review,health,audited=prepare(a.date)
    out,title=render(raw,review,health,audited); print(out)
    if a.reserve: send(raw,review,out,title,reserve_only=True)
if __name__=="__main__": main()
