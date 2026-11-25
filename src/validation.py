"""Single validation contract for local files, PRs, and audit handoffs."""
import datetime as dt
from src.common import SOURCE_MAP,digest,allowed_source
from src.digest import key

def text_fields(row,fields,limit=3000):
    if not isinstance(row,dict) or set(row)!=set(fields): raise ValueError("Unexpected row fields")
    if any(not isinstance(v,str) or not v.strip() or len(v)>limit for v in row.values()): raise ValueError("Missing or invalid text")
def iso_day(value):
    d=dt.date.fromisoformat(value)
    if str(d)!=value: raise ValueError("Date must be YYYY-MM-DD")
    return d
def strict_review(review):
    required={"schema","mode","run_date","collection_sha256","coverage","events"}
    if not isinstance(review,dict) or not required<=review.keys() or set(review)-required-{"changes"}: raise ValueError("Unexpected review fields")
    if type(review["schema"]) is not int or review["schema"]!=1: raise ValueError("Invalid schema")
    if not isinstance(review["events"],list) or not isinstance(review["coverage"],list) or not isinstance(review.get("changes",[]),list): raise ValueError("Invalid lists")
    if len(review["events"])>500 or len(review["coverage"])>100 or len(review.get("changes",[]))>100: raise ValueError("Too many rows")
    for c in review["coverage"]: text_fields(c,("institution","status","note"))
    for e in review["events"]: text_fields(e,("institution","title","date","url","relevance","certainty","why","evidence"))
    for c in review.get("changes",[]):
        text_fields(c,("institution","title","previous_date","kind","new_date","url","evidence"))
        if c["kind"] not in ("cancelled","rescheduled"): raise ValueError("Invalid change kind")
        if c["kind"]=="cancelled" and c["new_date"]!="-": raise ValueError("Cancelled event must have no new date")
        if c["kind"]=="rescheduled" and (iso_day(c["new_date"])==iso_day(c["previous_date"])): raise ValueError("Unchanged date")
    return review
def validate_collection(raw,date):
    if not isinstance(raw,dict) or raw.get("schema")!=1 or raw.get("run_date")!=str(date) or raw.get("mode") not in ("live","demo"): raise ValueError("Invalid collection")
    if not isinstance(raw.get("sources"),list) or not isinstance(raw.get("events"),list): raise ValueError("Invalid collection lists")
    names=[s["institution"] for s in raw["sources"]]
    if len(names)!=len(set(names)) or not names or any(n not in SOURCE_MAP for n in names): raise ValueError("Invalid source coverage")
    start=date+dt.timedelta(days=1); end=start+dt.timedelta(days=29)
    for e in raw["events"]:
        if e["institution"] not in names or not isinstance(e["title"],str) or not e["title"].strip() or not start<=iso_day(e["date"])<=end or not allowed_source(e["url"],SOURCE_MAP[e["institution"]]): raise ValueError("Invalid candidate")
    return raw
def validate_review(raw,review):
    strict_review(review)
    if review["run_date"]!=raw["run_date"] or review["collection_sha256"]!=digest(raw) or review["mode"]!=raw["mode"]: raise ValueError("Review does not match collection")
    expected={s["institution"] for s in raw["sources"]}
    covered=set()
    for c in review["coverage"]:
        name=c["institution"]
        if name not in expected or name in covered or c["status"] not in ("checked","partial","unavailable"): raise ValueError("Invalid coverage")
        covered.add(name)
    if covered!=expected: raise ValueError("Coverage must account for every source")
    start=iso_day(raw["run_date"])+dt.timedelta(days=1); end=start+dt.timedelta(days=29); seen=set()
    for e in review["events"]:
        if e["institution"] not in expected or not allowed_source(e["url"],SOURCE_MAP[e["institution"]],legacy_demo=raw["mode"]=="demo"): raise ValueError("Invalid primary URL")
        if e["relevance"] not in ("high","medium","calendar_only") or e["certainty"] not in ("confirmed","tentative"): raise ValueError("Invalid classification")
        if not start<=iso_day(e["date"])<=end: raise ValueError("Outside horizon")
        k=key(e)
        if k in seen: raise ValueError("Duplicate event")
        seen.add(k)
    change_keys=set()
    for c in review.get("changes",[]):
        if raw["mode"]!="live" or c["institution"] not in expected or not allowed_source(c["url"],SOURCE_MAP[c["institution"]]): raise ValueError("Invalid change source")
        if not start-dt.timedelta(days=7)<=iso_day(c["previous_date"])<=end: raise ValueError("Change outside comparison window")
        k=key({"institution":c["institution"],"title":c["title"],"date":c["previous_date"]})
        if k in change_keys: raise ValueError("Duplicate change")
        change_keys.add(k)
        if c["kind"]=="cancelled" and k in seen: raise ValueError("Cancelled event still listed as current")
        if c["kind"]=="rescheduled":
            new=iso_day(c["new_date"])
            if start<=new<=end and key({"institution":c["institution"],"title":c["title"],"date":c["new_date"]}) not in seen: raise ValueError("Rescheduled event missing")
    return review
