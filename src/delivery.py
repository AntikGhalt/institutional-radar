"""SMTP messages and persistent idempotent production reservations."""
import datetime as dt, hashlib, os, shutil, smtplib, ssl
from email.message import EmailMessage
from src.common import TZ,load,read,write
def send(root,raw,review,out,title,reserve_only=False,deliver=None):
    deliver=deliver or smtp_deliver
    if raw["mode"]!="live": raise ValueError("Synthetic demo must never be sent")
    if os.getenv("ENABLE_EMAIL")!="true": raise ValueError("Sending disabled")
    receipt=root/"data"/raw["run_date"]/"delivery.json"
    token=os.getenv("RADAR_DELIVERY_TOKEN","")
    if not token: raise ValueError("Delivery requires a workflow reservation token")
    if receipt.exists() and load(receipt).get("status")=="sent":
        print("Already delivered; no duplicate email."); return
    names=["report.html","calendar.ics","full-calendar.csv","digest-events.json"]+[str(p.relative_to(out)) for p in sorted((out/"calendar-events").glob("*.ics"))]
    files={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names}
    env={k:os.environ.get(k,"") for k in ("SMTP_USER","SMTP_PASSWORD","NOTIFY_TO")}
    if not all(env.values()): raise ValueError("SMTP credentials or recipient not configured")
    if reserve_only:
        if receipt.exists(): raise ValueError("Already reserved or attempted; inspect receipt before retry")
        published=receipt.parent/"calendar-events"
        if published.exists(): raise ValueError("Individual calendar files already published; inspect run")
        shutil.copytree(out/"calendar-events",published)
        shutil.copyfile(out/"digest-events.json",receipt.parent/"digest-events.json")
        write(receipt,{"status":"reserved","token":token,"at":dt.datetime.now(TZ).isoformat(),"files":files,"subject":title}); return
    if not receipt.exists(): raise ValueError("Missing persisted reservation")
    record=load(receipt)
    if record.get("status")!="reserved" or record.get("token")!=token or record.get("files")!=files: raise ValueError("Missing matching persisted reservation")
    if hashlib.sha256((receipt.parent/"digest-events.json").read_bytes()).hexdigest()!=files["digest-events.json"]: raise ValueError("Published digest manifest mismatch")
    for n in names:
        if n.startswith("calendar-events/") and hashlib.sha256((receipt.parent/n).read_bytes()).hexdigest()!=files[n]: raise ValueError("Published event file mismatch")
    msg=build_message(out,record["subject"],env)
    write(receipt,{"status":"attempting","at":dt.datetime.now(TZ).isoformat()})
    try: deliver(msg,env)
    except Exception:
        raise RuntimeError("SMTP attempt failed; inspect sender account before retry") from None
    write(receipt,{"status":"sent","at":dt.datetime.now(TZ).isoformat()})

def build_message(out,title,env):
    msg=EmailMessage(); msg["Subject"]=title; msg["From"]=env["SMTP_USER"]; msg["To"]=env["NOTIFY_TO"]
    msg.set_content("Agenda istituzionale: consultare la versione HTML e gli allegati.")
    msg.add_alternative(read(out/"report.html"),subtype="html")
    msg.add_attachment((out/"full-calendar.csv").read_bytes(),maintype="text",subtype="csv",filename="calendario-completo.csv")
    if b"BEGIN:VEVENT" in (out/"calendar.ics").read_bytes():
        msg.add_attachment((out/"calendar.ics").read_bytes(),maintype="text",subtype="calendar",filename="appuntamenti-selezionati.ics")
    return msg

def smtp_deliver(msg,env):
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST") or "smtp.gmail.com",int(os.getenv("SMTP_PORT") or "465"),context=ssl.create_default_context(),timeout=30) as smtp:
        smtp.login(env["SMTP_USER"],env["SMTP_PASSWORD"])
        if smtp.send_message(msg): raise RuntimeError("Recipient refused")

def send_test(raw,review,out,title,deliver=None):
    deliver=deliver or smtp_deliver
    if raw["mode"]!="live" or not review or not any(e["relevance"]!="calendar_only" for e in review["events"]):
        raise ValueError("Test email requires an existing live collection and nonempty editorial review")
    if os.getenv("ENABLE_EMAIL")!="true": raise ValueError("Sending disabled")
    env={k:os.environ.get(k,"") for k in ("SMTP_USER","SMTP_PASSWORD","NOTIFY_TO")}
    if not all(env.values()): raise ValueError("SMTP credentials or recipient not configured")
    try: deliver(build_message(out,"[TEST] "+title,env),env)
    except Exception: raise RuntimeError("Test SMTP attempt failed") from None
    print("Test email sent without a production delivery receipt.")

def check_production_date(date,today):
    if date>today: raise ValueError("Future production run: use preview or test_email with existing data.")

