"""Public source collection and immutable weekly snapshots."""
import concurrent.futures, datetime as dt, re
from html.parser import HTMLParser
from urllib.parse import urljoin
from src.calendars import adapter,fetch
from src.common import SOURCES,TZ,allowed_source,write
TERMS=re.compile(r"calendar|calendario|agenda|event|release|publication|pubblicazion|comunicat|statistic|rapport|report|news|notizi|studi",re.I)
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
        raw,base,enc=fetch(s["url"],s["domains"])
        if not allowed_source(base,s): raise ValueError("Unexpected redirect domain")
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
            dated,result["calendar_parser"]=adapter(s,start,end)
            result["dated_candidates"]=[e for e in dated if e.get("source_status")!="cancelled"]
            result["cancelled_candidates"]=[e for e in dated if e.get("source_status")=="cancelled"]
        except Exception as e:
            result["dated_candidates"]=[]; result["calendar_parser"]={"status":"error","attempts":[{"error":type(e).__name__}]}
    return result
def collect(root,date,demo=False):
    if demo: results=[{"institution":s["name"],"entry_url":s["url"],"links":[],"status":"demo_not_fetched"} for s in SOURCES]
    else:
        start=date+dt.timedelta(days=1); end=start+dt.timedelta(days=29)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: results=list(ex.map(lambda s:collect_one(s,start,end),SOURCES))
    raw={"schema":1,"run_date":str(date),"mode":"demo" if demo else "live","created_at":dt.datetime.now(TZ).isoformat(),"sources":results,"events":[e for s in results for e in s.get("dated_candidates",[])]}
    p=root/"data"/str(date)/"collection.json"
    if p.exists(): raise ValueError("Collection exists; do not overwrite")
    write(p,raw); return raw
