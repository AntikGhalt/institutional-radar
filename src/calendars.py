"""Deterministic calendar adapters. All results are candidates, never reviewed events."""
import datetime as dt
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

MONTHS="gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split()
WEEKDAYS="lunedì martedì mercoledì giovedì venerdì sabato domenica".split()
EUROSTAT_ICS="https://ec.europa.eu/eurostat/o/calendars/eventsIcal?theme=0&category=0"
ISTAT_ICS="https://www.google.com/calendar/ical/t49o0tm9m8f5c72l2gamob8djs%40group.calendar.google.com/public/basic.ics"
MAX_BYTES=12_000_000

def clean(s): return " ".join(s.split())
def month_year(text):
    m=re.fullmatch(r"("+"|".join(MONTHS)+r")\s+(20\d{2})",clean(text).casefold())
    return (int(m[2]),MONTHS.index(m[1])+1) if m else None

class Nodes(HTMLParser):
    """Collect leaf-ish HTML blocks, retaining document order and table cells."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack=[]; self.blocks=[]; self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ("br","hr"): self.handle_data(" "); return
        if tag in ("img","input","meta","link","source","area","wbr","col"): return
        self.stack.append([tag,attrs,[],[]])
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if self.stack and self.stack[-1][0]==tag: self.handle_endtag(tag)
    def handle_data(self,data):
        if data.strip():
            for n in self.stack: n[2].append(data.strip())
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag: break
        else: return
        n=self.stack[i]; del self.stack[i:]
        txt=clean(" ".join(n[2]))
        if tag in ("td","th"):
            for parent in reversed(self.stack):
                if parent[0]=="tr": parent[3].append(txt); break
        if tag=="a" and n[1].get("href"): self.links.append((n[1]["href"],txt))
        if tag in ("h1","h2","h3","h4","h5","h6","caption","p","strong","div","span","tr","li"):
            self.blocks.append((tag,txt,n[3],n[2]))

def parse_html(text):
    p=Nodes(); p.feed(text); return p

def source_candidate(institution,title,date,url,method,evidence,certainty="unknown"):
    return {"institution":institution,"title":clean(title)[:300],"date":date.isoformat(),"url":url,"method":method,"evidence":clean(evidence)[:600],"source_status":certainty}

def within(rows,start,end):
    unique={}
    for e in rows:
        d=dt.date.fromisoformat(e["date"])
        if start<=d<=end: unique.setdefault((e["institution"],e["date"],e["title"].casefold()),e)
    return sorted(unique.values(),key=lambda x:(x["date"],x["title"]))

def approved(url,hosts):
    p=urlsplit(url); h=p.hostname or ""
    return p.scheme=="https" and not p.username and not p.password and p.port in (None,443) and any(h==x or h.endswith("."+x) for x in hosts)

class SafeRedirect(HTTPRedirectHandler):
    def __init__(self,hosts): self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not approved(newurl,self.hosts): raise ValueError("Redirect outside approved hosts")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,hosts):
    if not approved(url,hosts): raise ValueError("URL outside approved hosts")
    with build_opener(SafeRedirect(hosts)).open(Request(url,headers={"User-Agent":"InstitutionalRadar/0.2 (public release calendar)"}),timeout=20) as r:
        body=r.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES: raise ValueError("Response exceeds limit")
        return body,r.geturl(),r.headers.get_content_charset() or "utf-8"

def unescape_ics(s): return re.sub(r"\\([nN,;\\])",lambda m:" " if m[1].lower()=="n" else m[1],s)
def ics_date(key,value):
    if re.fullmatch(r"\d{8}",value): return dt.datetime.strptime(value,"%Y%m%d").date()
    if not re.fullmatch(r"\d{8}T\d{6}Z?",value): raise ValueError("Invalid DTSTART")
    stamp=dt.datetime.strptime(value.rstrip("Z"),"%Y%m%dT%H%M%S")
    if value.endswith("Z"): stamp=stamp.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo("Europe/Rome"))
    elif "TZID=" in key:
        zone=key.split("TZID=",1)[1].split(";",1)[0].strip('"')
        stamp=stamp.replace(tzinfo=ZoneInfo(zone)).astimezone(ZoneInfo("Europe/Rome"))
    return stamp.date()

def parse_ics(text,institution,source,include_cancelled=False):
    text=re.sub(r"\r?\n[ \t]","",text)
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text: raise ValueError("Not an iCalendar response")
    events=[]; recognized=0
    for block in re.findall(r"(?ms)^BEGIN:VEVENT\r?\n(.*?)^END:VEVENT",text):
        props={}
        for line in block.splitlines():
            if ":" not in line: continue
            key,val=line.split(":",1); props[key.split(";",1)[0]]=(key,val)
        if not {"DTSTART","SUMMARY"}<=props.keys(): continue
        recognized+=1
        status=props.get("STATUS",("",""))[1].upper()
        if (status=="CANCELLED" and not include_cancelled) or "RRULE" in props: continue
        day=ics_date(*props["DTSTART"]); title=unescape_ics(props["SUMMARY"][1])
        events.append(source_candidate(institution,title,day,source,"ical",f"DTSTART={props['DTSTART'][1]}; SUMMARY={title}",status.lower() or "unknown"))
    if not recognized: raise ValueError("No recognizable VEVENT")
    return events

def inps_rows(text,source):
    rows=[]; current=None; recognized=0
    for tag,txt,cells,_ in parse_html(text).blocks:
        my=month_year(txt)
        if my: current=my
        if tag!="tr" or len(cells)<3 or current is None: continue
        match=re.fullmatch(r"([A-Za-zÀ-ÿ]+)\s*[-–]\s*(\d{1,2})",cells[2])
        if not match: continue
        year,month=current; day=dt.date(year,month,int(match[2]))
        if match[1].casefold()!=WEEKDAYS[day.weekday()]: raise ValueError("INPS weekday mismatch")
        recognized+=1
        rows.append(source_candidate("INPS",cells[0]+" – "+cells[1],day,source,"html_table"," | ".join(cells[:3])))
    if not recognized: raise ValueError("INPS table layout not recognized")
    return rows

def sisco_rows(text,source):
    rows=[]
    pattern=r"(?i)(Nota sulle Comunicazioni Obbligatorie|Rapporto Annuale sulle Comunicazioni Obbligatorie|Rapporto Immigrati)[^\n]*?"
    date_re=r"(\d{1,2})\s+("+"|".join(MONTHS)+r")\s+(20\d{2})\s*$"
    for line in text.splitlines():
        m=re.search(date_re,line.strip(),re.I); t=re.search(pattern,line)
        if not m or not t or m.start()<=t.start(): continue
        title=clean(line[t.start():m.start()])
        day=dt.date(int(m[3]),MONTHS.index(m[2].casefold())+1,int(m[1]))
        rows.append(source_candidate("MLPS",title,day,source,"pdf_table",line))
    if not rows: raise ValueError("SISCO PDF layout not recognized")
    return rows

def bank_rows(text,source,year,month):
    rows=[]; category=r"(?:Pubblicazioni|Statistiche|Convegni|Seminari|Appuntamenti|Interventi)"
    month_pattern=MONTHS[month-1]+r"|"+MONTHS[month-1][:3]+r"\.?"
    for tag,txt,cells,parts in parse_html(text).blocks:
        if tag!="li": continue
        m=re.match(r"^(\d{1,2})\s+(?:"+month_pattern+r")\s+(?:(\d{1,2})\s+(?:"+month_pattern+r")\s+)?("+category+r")\s+(.+)$",txt,re.I)
        if not m: continue
        day=dt.date(year,month,int(m[1])); title=clean(m[4])
        # The final text node is often a venue. Preserve raw evidence and avoid guessing its meaning.
        if len(parts)>1 and clean(parts[-1]) in ("Roma","Remoto","Francoforte","Milano","Online"): title=title.removesuffix(clean(parts[-1])).strip()
        rows.append(source_candidate("Banca d’Italia",title,day,source,"monthly_agenda",txt))
    if not rows: raise ValueError("Bank agenda layout not recognized")
    return rows

def pdf_text(body):
    if not body.startswith(b"%PDF"): raise ValueError("Expected PDF")
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"calendar.pdf"; p.write_bytes(body)
        result=subprocess.run(["pdftotext","-layout",str(p),"-"],capture_output=True,timeout=25,check=True)
        return result.stdout.decode("utf-8",errors="replace")

def adapter(source,start,end,sample_dir=None):
    name=source["name"]; url=source["url"]; hosts=source["domains"]; rows=[]; notes=[]; successful=0
    def attempt(label,fn):
        nonlocal successful
        try:
            got=fn(); rows.extend(got); successful+=1; notes.append({"method":label,"status":"parsed","rows":len(got)})
        except Exception as e:
            notes.append({"method":label,"status":"error","error":type(e).__name__,"http_status":getattr(e,"code",None)})
    def save_sample(label,text):
        if sample_dir is not None and text:
            sample_dir.mkdir(parents=True,exist_ok=True)
            (sample_dir/label).write_text(text,encoding="utf-8")
    def capture(label,fn):
        if sample_dir is not None:
            try: save_sample(label,fn())
            except Exception: pass # diagnostics do not affect collection
    def html_at(u):
        data,final,enc=fetch(u,hosts); return data.decode(enc,errors="replace"),final
    if name=="ISTAT":
        def istat_feeds():
            # Officially linked Google calendar is a public feed, not account access.
            data,_,enc=fetch(ISTAT_ICS,["google.com"])
            text=data.decode(enc,errors="replace")
            from src.fixtures import ical_excerpt
            capture("istat.ics" if name=="ISTAT" else "eurostat.ics",lambda:ical_excerpt(text))
            return parse_ics(text,name,url,include_cancelled=True)
        attempt("official_press_ical",istat_feeds)
        def discover():
            html,final=html_at(url); p=parse_html(html); feeds=set(); out=[]
            for href,_ in p.links:
                u=urljoin(final,href)
                if approved(u,["google.com"]) and "/public/basic.ics" in urlsplit(u).path and u!=ISTAT_ICS: feeds.add(u)
            for u in sorted(feeds)[:5]:
                data,_,enc=fetch(u,["google.com"]); out+=parse_ics(data.decode(enc,errors="replace"),name,url)
            if not feeds: raise ValueError("No additional public iCal links")
            return out
        attempt("additional_ical_discovery",discover)
    elif name=="Eurostat":
        def euro():
            data,_,enc=fetch(EUROSTAT_ICS,hosts)
            return parse_ics(data.decode(enc,errors="replace"),name,url)
        attempt("official_release_ical",euro)
    elif name=="INPS":
        def inps():
            html,final=html_at(url)
            from src.fixtures import table_excerpt
            capture("inps.html",lambda:table_excerpt(html,final))
            return inps_rows(html,final)
        attempt("observatory_table",inps)
    elif name=="MLPS":
        for year in sorted({start.year,end.year}):
            u=f"https://www.lavoro.gov.it/documenti-e-norme/studi-e-statistiche/calendario-diffusione-dati-sisco-{year}"
            def sisco(u=u):
                data,final,_=fetch(u,hosts); text=pdf_text(data)
                from src.fixtures import sisco_excerpt
                capture(f"sisco-{year}.txt",lambda:sisco_excerpt(text,final))
                return sisco_rows(text,final)
            attempt("sisco_pdf_"+str(year),sisco)
    elif name=="Banca d’Italia":
        for year,month in sorted({(start+dt.timedelta(days=i)).timetuple()[:2] for i in range((end-start).days+1)}):
            u=url+"?"+urlencode({"anno_pubblicazione":year,"mese_pubblicazione":f"{month:02d}"})
            def bank(u=u,year=year,month=month):
                html,final=html_at(u)
                from src.fixtures import agenda_excerpt
                capture(f"bank-{year}-{month:02d}.html",lambda:agenda_excerpt(html,final,year,month))
                return bank_rows(html,final,year,month)
            attempt(f"monthly_agenda_{year}_{month:02d}",bank)
    else: return [],{"status":"not_configured","attempts":[]}
    selected=within(rows,start,end)
    status="parsed_candidates" if successful==len(notes) and selected else "partial_candidates" if selected else "no_dated_candidates" if successful else "error"
    return selected,{"status":status,"attempts":notes,"candidate_count":len(selected)}
