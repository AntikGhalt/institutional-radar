"""Compare delivered editions without treating silence as cancellation."""
import datetime as dt
import hashlib
import json
from collections import defaultdict
from src.digest import key

def read_json(path): return json.loads(path.read_text(encoding="utf-8"))

def stable_uid(e):
    # Full date prevents collisions between repeated titles in the same edition.
    return hashlib.sha256(json.dumps(key(e),ensure_ascii=False).encode()).hexdigest()[:32]

def previous_records(data_dir,run_date):
    current=dt.date.fromisoformat(run_date)
    for folder in sorted(data_dir.glob("????-??-??"),reverse=True):
        try:
            day=dt.date.fromisoformat(folder.name)
            if day>=current or day.weekday()!=6: continue
            if read_json(folder/"delivery.json").get("status")!="sent": continue
            manifest=folder/"digest-events.json"
            if manifest.exists():
                record=read_json(manifest)
                if record.get("run_date")!=folder.name: continue
                events=record["events"]
            else:
                if read_json(folder/"collection.json").get("mode")!="live": continue
                events=[e for e in read_json(folder/"review.json")["events"] if e.get("relevance") in ("high","medium")]
            if not isinstance(events,list) or not events: continue
            return folder.name,{key(e):e for e in events}
        except (OSError,ValueError,KeyError,TypeError,AttributeError): continue
    return None,{}

def previous_edition(data_dir,run_date):
    baseline,rows=previous_records(data_dir,run_date)
    return baseline,set(rows)

def classify(data_dir,run_date,events):
    baseline,previous=previous_records(data_dir,run_date)
    if baseline is None: return None,{key(e):"baseline_unavailable" for e in events}
    return baseline,{key(e):"already_reported" if key(e) in previous else "new" for e in events}

def compare(data_dir,run_date,events,review,audited):
    baseline,previous=previous_records(data_dir,run_date)
    current={key(e):e for e in events}
    flags={k:("already_reported" if k in previous else "new" if baseline else "baseline_unavailable") for k in current}
    uids={k:previous.get(k,{}).get("uid") or stable_uid(e) for k,e in current.items()}
    # Reuse legacy UID only where it was actually unique in that edition.
    previous_names=defaultdict(list)
    for k in previous: previous_names[(k[0],k[2])].append(k)
    def prior_uid(k):
        old=previous[k]
        if old.get("uid"): return old["uid"]
        if len(previous_names[(k[0],k[2])])==1:
            # Legacy ICS hashed institution and original title, without date.
            return hashlib.sha256(json.dumps([old["institution"],old["title"]],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
        return stable_uid(old)
    for k in current.keys() & previous.keys(): uids[k]=prior_uid(k)
    notices=[]; moved=set(); explicit=set()
    if audited and baseline:
        for c in (review or {}).get("changes",[]):
            oldkey=key({"institution":c["institution"],"title":c["title"],"date":c["previous_date"]})
            if oldkey not in previous or oldkey in current: continue
            if c["kind"]=="cancelled":
                notices.append({**c,"status":"cancelled"}); explicit.add(oldkey)
            else:
                newkey=key({"institution":c["institution"],"title":c["title"],"date":c["new_date"]})
                if newkey not in current or current[newkey]["certainty"]!="confirmed": continue
                status="postponed" if c["new_date"]>c["previous_date"] else "advanced"
                flags[newkey]=status; uids[newkey]=prior_uid(oldkey)
                notices.append({**c,"status":status}); moved.add(newkey); explicit.add(oldkey)
    # Same-title differing dates alone are hints, never verified reschedules.
    # Only compare unique unmatched titles, and distinguish from new publications.
    if baseline:
        unmatched_old=defaultdict(list); unmatched_new=defaultdict(list)
        start=(dt.date.fromisoformat(run_date)+dt.timedelta(days=1)).isoformat()
        for k in previous:
            if k not in current and k not in explicit and k[1]>=start: unmatched_old[(k[0],k[2])].append(k)
        for k in current:
            if k not in previous and k not in moved: unmatched_new[(k[0],k[2])].append(k)
        for ident,ks in unmatched_new.items():
            olds=unmatched_old.get(ident,[])
            if len(ks)==len(olds)==1 and len(previous_names[ident])==1:
                k=ks[0]; flags[k]="date_changed_unverified"
                notices.append({"institution":k[0],"title":current[k]["title"],"previous_date":olds[0][1],"new_date":k[1],"url":current[k]["url"],"evidence":"Data diversa tra le edizioni; rinvio o nuova uscita non ancora verificati.","status":"date_changed_unverified"})
    # Defensive collision check for legacy IDs and overlapping moved entries.
    used=set()
    for k in sorted(uids):
        if uids[k] in used: uids[k]=stable_uid(current[k])
        used.add(uids[k])
    return baseline,flags,uids,notices
