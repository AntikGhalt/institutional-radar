"""Shared paths, source configuration and JSON utilities."""
import datetime as dt, hashlib, json, os
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Europe/Rome")
SOURCES=json.loads((ROOT/"config/sources.json").read_text(encoding="utf-8"))
SOURCE_MAP={s["name"]:s for s in SOURCES}
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

def repository():
    return os.getenv("RADAR_REPOSITORY") or os.getenv("GITHUB_REPOSITORY") or "AntikGhalt/institutional-radar"
def scheduled_sunday(today):
    return today-dt.timedelta(days=(today.weekday()+1)%7)
