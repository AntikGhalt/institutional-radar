"""Institutional Radar: collection, review validation, preview and gated delivery."""
import argparse, concurrent.futures, datetime as dt, hashlib, html, json, os, re, smtplib, ssl
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
def collect_one(s):
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
    return result
def collect(date,demo=False):
    if demo: results=[{"institution":s["name"],"entry_url":s["url"],"links":[],"status":"demo_not_fetched"} for s in SOURCES]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: results=list(ex.map(collect_one,SOURCES))
    raw={"schema":1,"run_date":str(date),"mode":"demo" if demo else "live","created_at":dt.datetime.now(TZ).isoformat(),"sources":results,"events":[]}
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
        if e["relevance"] not in ("high","medium") or e["certainty"] not in ("confirmed","tentative"): raise ValueError("Invalid classification")
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
def render(raw,review):
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1)
    events=sorted(review["events"],key=lambda e:(e["date"],e["institution"])) if review else []
    title=f"Radar istituzionale | {start:%d/%m/%Y} – {start+dt.timedelta(days=29):%d/%m/%Y}"
    warning="DEMO — nessun evento reale." if raw["mode"]=="demo" else ("Revisione assente: invio bloccato." if review is None else "Date riportate dalla revisione: validazione strutturale, non verifica fattuale indipendente.")
    h=[f'<!doctype html><html lang="it"><meta charset="utf-8"><body style="font-family:Arial,sans-serif;max-width:780px;margin:auto"><h1>{esc(title)}</h1><p><strong>{esc(warning)}</strong></p>']
    for low,high,label in [(0,6,"Settimana in arrivo"),(7,20,"Due settimane successive"),(21,29,"Resto dei 30 giorni")]:
        h.append(f"<h2>{label}</h2>")
        group=[e for e in events if low<=(dt.date.fromisoformat(e["date"])-start).days<=high]
        if not group: h.append("<p>Nessun appuntamento verificato in questa sezione.</p>")
        for e in group:
            h.append(f'<p><strong>{esc(e["date"])} — {esc(e["institution"])} — {esc(e["title"])}</strong><br>{esc(e["why"])}<br>{esc(e["certainty"])} · {esc(e["relevance"])} · <a href="{esc(e["url"])}">Fonte ufficiale</a></p>')
    h.append("<h2>Copertura e limiti</h2>")
    coverage={c["institution"]:c for c in review["coverage"]} if review else {}
    for s in raw["sources"]:
        c=coverage.get(s["institution"],{}); h.append(f'<p>{esc(s["institution"])}: Python {esc(s["status"])}; revisione {esc(c.get("status","assente"))}. {esc(c.get("note",s.get("error","")))}</p>')
    h.append("</body></html>")
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Institutional Radar//IT","CALSCALE:GREGORIAN"]
    if raw["mode"]=="live":
        for e in events:
            if e["certainty"]!="confirmed" or e["relevance"]!="high": continue
            d=dt.date.fromisoformat(e["date"]); uid=digest([e["institution"],e["title"]])[:32]+"@institutional-radar"
            lines+=["BEGIN:VEVENT","UID:"+uid,"DTSTAMP:"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),"DTSTART;VALUE=DATE:"+d.strftime("%Y%m%d"),"DTEND;VALUE=DATE:"+(d+dt.timedelta(days=1)).strftime("%Y%m%d"),"SUMMARY:"+ics_escape(e["institution"]+" — "+e["title"]),"DESCRIPTION:"+ics_escape(e["why"]+"\n"+e["url"]),"TRANSP:TRANSPARENT","END:VEVENT"]
    lines.append("END:VCALENDAR"); out=ROOT/"output"/raw["run_date"]; out.mkdir(parents=True,exist_ok=True)
    (out/"report.html").write_text("\n".join(h),encoding="utf-8"); (out/"calendar.ics").write_bytes(("\r\n".join(map(fold,lines))+"\r\n").encode()); return out,title
def send(raw,review,out,title):
    if raw["mode"]!="live" or review is None: raise ValueError("Sending blocked: requires live validated review")
    if os.getenv("ENABLE_EMAIL")!="true": raise ValueError("Sending disabled")
    receipt=ROOT/"data"/raw["run_date"]/"delivery.json"
    if receipt.exists(): raise ValueError("Already sent or attempted; inspect receipt before retry")
    env={k:os.environ.get(k,"") for k in ("SMTP_USER","SMTP_PASSWORD","NOTIFY_TO")}
    if not all(env.values()): raise ValueError("SMTP credentials or recipient not configured")
    msg=EmailMessage(); msg["Subject"]=title; msg["From"]=env["SMTP_USER"]; msg["To"]=env["NOTIFY_TO"]; msg.set_content("Agenda istituzionale: consultare la versione HTML."); msg.add_alternative(read(out/"report.html"),subtype="html"); msg.add_attachment((out/"calendar.ics").read_bytes(),maintype="text",subtype="calendar",filename="calendar.ics")
    write(receipt,{"status":"attempting","at":dt.datetime.now(TZ).isoformat()})
    try:
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST") or "smtp.gmail.com",int(os.getenv("SMTP_PORT") or "465"),context=ssl.create_default_context(),timeout=30) as smtp:
            smtp.login(env["SMTP_USER"],env["SMTP_PASSWORD"])
            if smtp.send_message(msg): raise RuntimeError("Recipient refused")
    except Exception:
        raise RuntimeError("SMTP attempt failed; inspect sender account before retry") from None
    write(receipt,{"status":"sent","at":dt.datetime.now(TZ).isoformat()})
def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["collect","demo-review","finalize","hash"]); p.add_argument("--date",type=dt.date.fromisoformat,default=run_date()); p.add_argument("--demo",action="store_true"); p.add_argument("--send",action="store_true"); a=p.parse_args()
    if a.date.weekday()!=6: p.error("Run date must be a Sunday")
    directory=ROOT/"data"/str(a.date)
    if a.command=="collect": collect(a.date,a.demo); return
    raw=load(directory/"collection.json")
    if a.command=="hash": print(digest(raw)); return
    if a.command=="demo-review":
        if raw["mode"]!="demo": raise SystemExit("Demo only")
        write(directory/"review.json",make_demo_review(raw)); return
    review=validate_review(raw,load(directory/"review.json")) if (directory/"review.json").exists() else None
    out,title=render(raw,review); print(out)
    if a.send: send(raw,review,out,title)
if __name__=="__main__": main()
