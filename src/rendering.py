"""Digest HTML, calendar and spreadsheet rendering."""
import datetime as dt, html, shutil
from src.common import SOURCE_MAP,allowed_source,digest,write,repository
from src.digest import full_rows,write_csv,health_html,key
from src.calendar_links import calendar_links,individual_ics_url
from src.history import compare,stable_uid
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
    return e.get("uid") or stable_uid(e)

def event_lines(e,stamp):
    d=dt.date.fromisoformat(e["date"])
    return ["BEGIN:VEVENT","UID:"+event_uid(e)+"@institutional-radar","DTSTAMP:"+stamp,"DTSTART;VALUE=DATE:"+d.strftime("%Y%m%d"),"DTEND;VALUE=DATE:"+(d+dt.timedelta(days=1)).strftime("%Y%m%d"),"SUMMARY:"+ics_escape(e["institution"]+" — "+e["title"]),"DESCRIPTION:"+ics_escape(e["why"]+"\n"+e["url"]),"TRANSP:TRANSPARENT","END:VEVENT"]

def ics_bytes(events,stamp):
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Institutional Radar//IT","CALSCALE:GREGORIAN"]
    for e in events: lines+=event_lines(e,stamp)
    lines.append("END:VCALENDAR")
    return ("\r\n".join(map(fold,lines))+"\r\n").encode()

def render(root,raw,review,health=None,audited=False,publish_links=True):
    from src.spreadsheet import write_xlsx
    start=dt.date.fromisoformat(raw["run_date"])+dt.timedelta(days=1)
    events=sorted((e for e in (review or {}).get("events",[]) if e["relevance"]!="calendar_only"),key=lambda e:(e["date"],e["institution"],e["title"]))
    baseline,novelty,uids,notices=compare(root/"data",raw["run_date"],events,review,audited) if raw["mode"]=="live" else (None,{},{},[])
    events=[dict(e,uid=uids.get(key(e),stable_uid(e))) for e in events]
    numbering={key(e):i for i,e in enumerate(events,1)}
    out=root/"output"/raw["run_date"]; out.mkdir(parents=True,exist_ok=True)
    individual_dir=out/"calendar-events"
    if individual_dir.exists(): shutil.rmtree(individual_dir)
    individual_dir.mkdir()
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    eligible=[e for e in events if raw["mode"]=="live" and audited and e["certainty"]=="confirmed" and novelty.get(key(e))!="date_changed_unverified"]
    individual={}
    for e in eligible:
        uid=event_uid(e)
        (individual_dir/(uid+".ics")).write_bytes(ics_bytes([e],stamp))
        if publish_links: individual[key(e)]=individual_ics_url(raw["run_date"],uid)
    rows=full_rows(raw,review,audited,lambda url,name: name in SOURCE_MAP and allowed_source(url,SOURCE_MAP[name],legacy_demo=raw["mode"]=="demo"),individual,numbering,novelty,notices)
    title=f"Radar istituzionale | {start:%d/%m/%Y} – {start+dt.timedelta(days=29):%d/%m/%Y}"
    warning="DEMO — nessun evento reale." if raw["mode"]=="demo" else ("Nessuna selezione editoriale disponibile. Il calendario allegato contiene soltanto i candidati recuperati." if review is None else "Selezione verificata dall’audit indipendente, nei limiti indicati." if audited else "Selezione disponibile, ma audit indipendente assente: date non ricontrollate dal secondo agente.")
    if health and health["critical"]: title="[CRITICO] "+title
    elif health and health["degraded"]: title="[PARZIALE] "+title
    h=[f'<!doctype html><html lang="it"><meta charset="utf-8"><body style="font-family:Arial,sans-serif;max-width:780px;margin:auto"><h1>{esc(title)}</h1><p><strong>{esc(warning)}</strong></p>']
    if health and health["critical"]: h.append("<p><strong>PROBLEMA CRITICO: almeno una fase è priva di una consegna verificata da due settimane consecutive.</strong></p>")
    if health and health["degraded"]: h.append(health_html(health))
    h.append(f"<p>{len(events)} appuntamenti selezionati · {len(rows)} voci nel calendario completo.</p>")
    if baseline:
        n_new=sum(v=="new" for v in novelty.values())
        n_old=sum(v=="already_reported" for v in novelty.values())
        n_changed=len(events)-n_new-n_old
        h.append(f"<p><strong>{n_new} nuovi</strong> · {n_old} già segnalati · {n_changed} con data variata o da verificare, rispetto al digest del {dt.date.fromisoformat(baseline):%d/%m/%Y}.</p>")
    elif raw["mode"]=="live" and events:
        h.append("<p>Nessun digest precedente con appuntamenti disponibile per il confronto.</p>")
    if raw["mode"]=="live" and not raw.get("events"): h.append("<p>Attenzione: nessun candidato datato nella raccolta Python; il calendario allegato contiene soltanto gli eventi individuati nella revisione, se disponibile.</p>")
    if notices:
        h.append("<h2>Variazioni rispetto all’ultima edizione</h2>")
        labels={"cancelled":"CANCELLATO","postponed":"RINVIATO","advanced":"ANTICIPATO","date_changed_unverified":"DATA DIVERSA — DA VERIFICARE"}
        for n in notices:
            h.append(f'<p><strong>{esc(labels[n["status"]])} · {esc(n["institution"])} — {esc(n["title"])}</strong><br>{esc(n["previous_date"])} → {esc(n["new_date"])} · <a href="{esc(n["url"])}">Fonte</a><br>{esc(n["evidence"])}</p>')
    for low,high,label in [(0,6,"Settimana in arrivo"),(7,20,"Due settimane successive"),(21,29,"Resto dei 30 giorni")]:
        h.append(f"<h2>{label}</h2>")
        group=[e for e in events if low<=(dt.date.fromisoformat(e["date"])-start).days<=high]
        if not group: h.append("<p>Nessun appuntamento selezionato in questa sezione.</p>")
        for e in group:
            extras=""
            if raw["mode"]=="live" and audited and e["certainty"]=="confirmed" and novelty.get(key(e))!="date_changed_unverified":
                link=calendar_links(e,verified=True)
                extras=f' · Aggiungi: <a href="{esc(link["google"])}">Google Calendar</a> | <a href="{esc(link["outlook"])}">Outlook</a>'
                if key(e) in individual: extras+=f' | <a href="{esc(individual[key(e)])}">.ics</a>'
            flag=novelty.get(key(e))
            marker=' <strong style="color:#1463a3">[NUOVO]</strong>' if flag=="new" else ' <span style="color:#666">[Già segnalato]</span>' if flag=="already_reported" else ""
            if flag in ("postponed","advanced","date_changed_unverified"):
                marker=' <strong style="color:#976213">['+{"postponed":"RINVIATO","advanced":"ANTICIPATO","date_changed_unverified":"DATA DA VERIFICARE"}[flag]+']</strong>'
            h.append(f'<p><strong>{numbering[key(e)]}. {esc(e["date"])} — {esc(e["institution"])} — {esc(e["title"])}</strong>{marker}<br>{esc(e["why"])}<br>{"Confermata nella revisione" if e["certainty"]=="confirmed" else "Provvisoria"} · {"Alta" if e["relevance"]=="high" else "Media"} · <a href="{esc(e["url"])}">Fonte ufficiale</a>{extras}</p>')
    if health and not health["degraded"]: h.append(health_html(health))
    h.append("<h2>Copertura e limiti</h2>")
    coverage={c["institution"]:c for c in review["coverage"]} if review else {}
    counts={state:sum(c["status"]==state for c in coverage.values()) for state in ("checked","partial","unavailable")}
    if coverage:
        h.append(f'<p>Fonti verificate: {counts["checked"]}; parziali: {counts["partial"]}; non disponibili: {counts["unavailable"]}. <a href="https://github.com/{esc(repository())}/tree/main/data/{esc(raw["run_date"])}">Dettagli e dati della rilevazione</a>.</p>')
    for s in raw["sources"]:
        c=coverage.get(s["institution"],{})
        if c.get("status")=="checked": continue
        h.append(f'<p style="font-size:13px">{esc(s["institution"])}: Python {esc(s["status"])}; revisione {esc(c.get("status","assente"))}. {esc(c.get("note",s.get("error","")))}</p>')
    metrics=(health or {}).get("metrics",{})
    if metrics:
        h.append(f"<h2>Contributo delle fasi</h2><p>Python: {metrics.get('python_candidates',0)} candidati distinti; Claude: {esc(metrics.get('claude_selected') if metrics.get('claude_selected') is not None else 'non misurabile')} selezioni; audit: {esc(metrics.get('audit_added_selected') if metrics.get('audit_added_selected') is not None else 'non misurabile')} aggiunte. Dettagli nel file Excel.</p>")
    h.append(f"<p>Excel: {len(rows)} appuntamenti recuperati, con stato e collegamenti per aggiungere singole voci. I candidati non verificati aprono bozze contrassegnate «Da verificare». L’ICS cumulativo include solo eventi selezionati di alta rilevanza con data confermata e audit valido. I link individuali .ics sono pubblicati con l’invio.</p></body></html>")
    (out/"report.html").write_text("\n".join(h),encoding="utf-8")
    (out/"calendar.ics").write_bytes(ics_bytes([e for e in eligible if e["relevance"]=="high"],stamp))
    write_csv(out/"full-calendar.csv",rows) # machine-readable artifact, not emailed
    write_xlsx(out/"full-calendar.xlsx",rows,notices,metrics)
    write(out/"metrics.json",metrics)
    write(out/"digest-events.json",{"schema":1,"run_date":raw["run_date"],"events":[{k:e[k] for k in ("institution","title","date","uid")} for e in events]})
    return out,title
