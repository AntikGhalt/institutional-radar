"""Weekly digest rendering, full calendar export and health history."""
import csv
import datetime as dt
import html
import json
import re
import unicodedata
from pathlib import Path
from src.calendar_links import calendar_links

def esc(x): return html.escape(str(x),quote=True)
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def key(e):
    text=unicodedata.normalize("NFKC",e["title"]).casefold()
    return e["institution"],e["date"],re.sub(r"\W+"," ",text).strip()

def weekly_health(data,run,stages):
    prior=data/str(dt.date.fromisoformat(run)-dt.timedelta(days=7))/"health.json"
    previous={}
    if prior.is_file():
        try: previous=load(prior).get("stages",{})
        except (ValueError,OSError): pass
    result={}
    for name,(state,note) in stages.items():
        old=previous.get(name,{})
        streak=0 if state=="ok" else 1+int(old.get("missed_weeks",0))
        result[name]={"status":state,"note":note,"missed_weeks":streak}
    return {"schema":1,"run_date":run,"stages":result,"critical":any(v["missed_weeks"]>=2 for v in result.values()),"degraded":any(v["status"]!="ok" for v in result.values())}

def full_rows(raw,review,audited,allow,individual=None,numbering=None,novelty=None):
    rows={}
    for e in raw.get("events",[]):
        try:
            if not allow(e["url"],e["institution"]): continue
            rows[key(e)]={"date":e["date"],"institution":e["institution"],"title":e["title"],"url":e["url"],"status":"Candidato Python – non verificato","selected":"No","method":e.get("method",""),"evidence":e.get("evidence","")}
        except (KeyError,TypeError,ValueError): continue
    for e in (review or {}).get("events",[]):
        status=("Data provvisoria" if e["certainty"]=="tentative" else "Confermata nella revisione")
        if not audited: status+=" – audit indipendente assente"
        old=rows.get(key(e),{})
        rows[key(e)]={"date":e["date"],"institution":e["institution"],"title":e["title"],"url":e["url"],"status":status,"selected":"No" if e.get("relevance")=="calendar_only" else "Sì","method":old.get("method","Revisione"),"evidence":e["evidence"]}
    for row in rows.values():
        if raw.get("mode")=="demo": continue
        try:
            row.update(calendar_links(row,verified=audited and row["status"]=="Confermata nella revisione"))
            row["ics"]=(individual or {}).get(key(row),"")
        except (ValueError,KeyError,TypeError): pass
    ordered=sorted(rows.values(),key=lambda e:(e["date"],e["institution"],e["title"]))
    labels={"new":"Nuovo","already_reported":"Già segnalato","baseline_unavailable":"Non confrontabile","postponed":"Rinviato","advanced":"Anticipato","date_changed_unverified":"Data diversa da verificare"}
    for i,row in enumerate(ordered,1):
        row["calendar_number"]=i
        row["digest_number"]=(numbering or {}).get(key(row),"")
        row["novelty"]=labels.get((novelty or {}).get(key(row)),"") if row["selected"]=="Sì" else ""
    return ordered

def cell(v):
    s=str(v)
    # Prevent spreadsheet formula injection from external source text.
    return "'"+s if s.lstrip().startswith(("=","+","-","@")) or s.startswith(("\t","\r","\n")) else s

def write_csv(path,rows):
    fields=["calendar_number","digest_number","novelty","date","institution","title","url","status","selected","method","evidence","google","outlook","ics"]
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["N. calendario","N. digest","Novità nel digest","Data","Ente","Titolo","Fonte","Stato verifica","Nel digest","Metodo","Evidenza","Aggiungi a Google Calendar","Aggiungi a Outlook (web)","File ICS individuale (se disponibile)"])
        for e in rows: w.writerow([cell(e.get(k,"")) for k in fields])

def health_html(health):
    if not health: return ""
    lines=["<h2>Controlli di esecuzione</h2><table style='border-collapse:collapse;font-size:14px;width:100%'>"]
    labels={"python":"Raccolta Python","parser_quality":"Qualità dei parser","claude":"Revisione Claude","chatgpt":"Audit ChatGPT"}
    names={"ok":"Completato","missing":"Consegna assente","invalid":"Consegna non valida","unknown":"Non verificabile","partial":"Parziale"}
    for k,v in health["stages"].items():
        state=names.get(v["status"],v["status"])
        extra=f" – {v['missed_weeks']} settimane consecutive senza consegna verificata" if v["missed_weeks"] else ""
        lines.append(f"<tr><td style='padding:5px;border-bottom:1px solid #ddd'><strong>{esc(labels.get(k,k))}</strong></td><td style='padding:5px;border-bottom:1px solid #ddd'>{esc(state+extra)}<br><small>{esc(v['note'])}</small></td></tr>")
    lines.append("</table><p style='font-size:12px'>Lo stato indica consegne verificabili, non la causa di un eventuale mancato avvio. Le quote dei servizi AI non sono osservabili da GitHub.</p>")
    return "".join(lines)
