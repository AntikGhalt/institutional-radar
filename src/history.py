"""Compare editorial entries with the last substantive delivered edition."""
import datetime as dt
import json
from src.digest import key

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def previous_edition(data_dir, run_date):
    current=dt.date.fromisoformat(run_date)
    for folder in sorted(data_dir.glob("????-??-??"), reverse=True):
        try:
            day=dt.date.fromisoformat(folder.name)
            if day>=current or day.weekday()!=6: continue
            receipt=read_json(folder/"delivery.json")
            if receipt.get("status")!="sent": continue
            manifest=folder/"digest-events.json"
            if manifest.exists():
                record=read_json(manifest)
                if record.get("run_date")!=folder.name: continue
                events=record["events"]
            else:
                # Legacy editions predate the exact selection manifest.
                raw=read_json(folder/"collection.json")
                if raw.get("mode")!="live": continue
                review=read_json(folder/"review.json")
                events=[e for e in review["events"] if e.get("relevance") in ("high","medium")]
            if not isinstance(events,list) or not events: continue
            return folder.name,{key(e) for e in events}
        except (OSError,ValueError,KeyError,TypeError,AttributeError): continue
    return None,set()

def classify(data_dir,run_date,events):
    baseline,previous=previous_edition(data_dir,run_date)
    if baseline is None: return None,{key(e):"baseline_unavailable" for e in events}
    return baseline,{key(e):"already_reported" if key(e) in previous else "new" for e in events}
