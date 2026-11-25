"""Delivery authorization binds an independent audit to exact collection/review bytes."""
import hashlib, re
from pathlib import Path

def blob_sha(path):
    data=Path(path).read_bytes()
    return hashlib.sha1(("blob "+str(len(data))+"\0").encode()+data).hexdigest()

def validate_audit(directory,raw,review,record):
    if raw["mode"]!="live" or review is None: raise ValueError("Live review required")
    keys={"schema","run_date","collection_blob_sha","review_blob_sha","status","auditor","summary","limitations"}
    if not isinstance(record,dict) or not keys<=record.keys() or set(record)-keys-{"claude_review_commit"} or record["schema"]!=1 or record["run_date"]!=raw["run_date"]: raise ValueError("Invalid audit schema/date")
    if record["status"]!="approved" or record["auditor"]!="ChatGPT": raise ValueError("Independent audit not approved")
    if not all(isinstance(record[k],str) and record[k].strip() and len(record[k])<=8000 for k in ("summary","limitations")): raise ValueError("Missing audit evidence")
    if record["collection_blob_sha"]!=blob_sha(directory/"collection.json") or record["review_blob_sha"]!=blob_sha(directory/"review.json"): raise ValueError("Audit no longer matches reviewed bytes")
    if "claude_review_commit" in record and not re.fullmatch(r"[0-9a-f]{40}",record["claude_review_commit"]): raise ValueError("Invalid Claude baseline commit")
    return record
