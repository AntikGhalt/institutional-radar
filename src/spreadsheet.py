"""Native Excel calendar with clickable HTTPS links and safe literal cells."""
import datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Alignment,Font,PatternFill
from openpyxl.utils import get_column_letter

FIELDS=[
 ("calendar_number","N. calendario",13),("digest_number","N. email",11),("novelty","Novità",24),
 ("date","Data",14),("institution","Ente",24),("title","Titolo",64),("status","Stato verifica",44),
 ("selected","Nel digest",12),("relevance","Rilevanza",18),("url","Fonte ufficiale",22),("google","Google Calendar",20),
 ("outlook","Outlook",16),("ics","ICS individuale",17),("method","Metodo",24),("evidence","Evidenza",70)
]
LINKS={"url":"Apri fonte","google":"Aggiungi","outlook":"Aggiungi","ics":"Scarica .ics"}
def literal(c,value):
    c.value=str(value)
    c.data_type="s"  # no formula evaluation of external text

def decorate(ws,widths):
    ws.freeze_panes="G2" if ws.title=="Calendario" else "A2"
    ws.auto_filter.ref=ws.dimensions
    ws.row_dimensions[1].height=29
    for c in ws[1]:
        c.fill=PatternFill("solid",fgColor="234E64"); c.font=Font(name="Arial",size=11,bold=True,color="FFFFFF")
        c.alignment=Alignment(vertical="center",wrap_text=True)
    for i,w in enumerate(widths,1): ws.column_dimensions[get_column_letter(i)].width=w
    ws.sheet_view.showGridLines=False

def write_xlsx(path,rows,notices=(),metrics=None):
    wb=Workbook(); ws=wb.active; ws.title="Calendario"
    ws.append([x[1] for x in FIELDS])
    for i,e in enumerate(rows,2):
        ws.row_dimensions[i].height=33
        for j,(field,_,_) in enumerate(FIELDS,1):
            c=ws.cell(i,j); val=e.get(field,"")
            c.font=Font(name="Arial",size=11)
            c.alignment=Alignment(vertical="center",wrap_text=field in ("title","status","evidence","novelty"))
            if i%2==0: c.fill=PatternFill("solid",fgColor="F2F6F8")
            if field=="date" and val:
                c.value=dt.date.fromisoformat(val); c.number_format="dd/mm/yyyy"
            elif field in ("calendar_number","digest_number") and isinstance(val,int): c.value=val
            elif field in LINKS and isinstance(val,str) and val.startswith("https://"):
                literal(c,LINKS[field]); c.hyperlink=val; c.font=Font(name="Arial",size=11,color="1463A3",underline="single")
            else: literal(c,val)
            if field=="novelty" and val in ("Nuovo","Rinviato","Anticipato"): c.font=Font(name="Arial",size=11,bold=True,color="1463A3")
    decorate(ws,[x[2] for x in FIELDS])
    ws=wb.create_sheet("Variazioni")
    headers=["Ente","Titolo","Data precedente","Nuova data","Stato","Fonte","Evidenza"]
    ws.append(headers)
    labels={"cancelled":"Cancellato","postponed":"Rinviato","advanced":"Anticipato","date_changed_unverified":"Data diversa da verificare"}
    for i,n in enumerate(notices,2):
        vals=[n["institution"],n["title"],n["previous_date"],n.get("new_date","-"),labels[n["status"]],n["url"],n["evidence"]]
        for j,v in enumerate(vals,1):
            c=ws.cell(i,j); literal(c,v); c.font=Font(name="Arial",size=11); c.alignment=Alignment(vertical="center",wrap_text=True)
            if j in (3,4) and v!="-": c.value=dt.date.fromisoformat(v); c.number_format="dd/mm/yyyy"
            if j==6 and v.startswith("https://"): c.value="Apri fonte"; c.hyperlink=v; c.font=Font(name="Arial",size=11,color="1463A3",underline="single")
        ws.row_dimensions[i].height=34
    decorate(ws,[23,64,17,17,30,20,76])
    ws=wb.create_sheet("Metriche")
    ws.append(["Indicatore","Valore"])
    if metrics:
        labels={"python_candidates":"Candidati Python (distinti)","claude_selected":"Voci selezionate da Claude","claude_new_vs_python":"Selezioni Claude non abbinate a Python","audit_added_selected":"Selezioni aggiunte nell'audit","audit_removed_selected":"Selezioni rimosse o declassate nell'audit","audit_changed_fields":"Voci comuni con campi modificati","final_selected":"Selezioni finali","claude_baseline":"Provenienza del confronto Claude","method":"Metodo e limiti"}
        for k,v in metrics.items():
            if k not in labels: continue
            ws.append([labels[k],v if type(v) is int else None])
            if type(v) is not int: literal(ws.cell(ws.max_row,2),"Non misurabile" if v is None else v)
    decorate(ws,[53,92])
    for row in ws.iter_rows(min_row=2):
        for c in row: c.font=Font(name="Arial",size=11); c.alignment=Alignment(wrap_text=True,vertical="center")
    wb.save(path)
