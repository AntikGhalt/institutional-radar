"""Accept only validated, owner-authored, same-repository review-data PRs.

Never check out or execute pull request code. GitHub's API supplies JSON data.
"""
import base64
import datetime as dt
import json
import os
import re
import subprocess
from src import radar

def api(path,*args):
    p=subprocess.run(["gh","api",path,*args],capture_output=True,text=True,check=True,timeout=60)
    return json.loads(p.stdout)

def check_pr(pr,repo,owner,files):
    head=pr["head"]
    if pr["state"]!="open" or pr["draft"] or pr["base"]["ref"]!="main": raise ValueError("Not an open review PR")
    if not head.get("repo") or head["repo"]["full_name"]!=repo or pr["user"]["login"]!=owner or not head["ref"].startswith("claude/"): raise ValueError("Untrusted review origin")
    if pr["changed_files"]!=1 or len(files)!=1: raise ValueError("Expected exactly one changed file")
    f=files[0]
    m=re.fullmatch(r"data/(\d{4}-\d{2}-\d{2})/review\.json",f["filename"])
    if not m or f["status"]!="added": raise ValueError("Only new review.json files allowed")
    d=dt.date.fromisoformat(m[1])
    if d.weekday()!=6: raise ValueError("Invalid run date")
    return f["filename"],d,head["sha"]

def strict_review(review):
    if set(review)!={"schema","mode","run_date","collection_sha256","coverage","events"}: raise ValueError("Unexpected review fields")
    if len(review["events"])>200 or len(review["coverage"])>100: raise ValueError("Too many rows")
    for row,keys in [(c,{"institution","status","note"}) for c in review["coverage"]]+[(e,{"institution","title","date","url","relevance","certainty","why","evidence"}) for e in review["events"]]:
        if set(row)!=keys or any(not isinstance(v,str) or len(v)>3000 for v in row.values()): raise ValueError("Unexpected row fields")
    return review

def main():
    repo=os.environ["GITHUB_REPOSITORY"]; owner=os.environ["GITHUB_REPOSITORY_OWNER"]; num=int(os.environ["PR_NUMBER"])
    endpoint=f"repos/{repo}/pulls/{num}"
    pr=api(endpoint); files=api(endpoint+"/files?per_page=2")
    path,date,sha=check_pr(pr,repo,owner,files)
    raw=radar.load(radar.ROOT/"data"/str(date)/"collection.json")
    if raw["mode"]=="live" and date!=radar.run_date(): raise ValueError("Stale or unexpected live run")
    if (radar.ROOT/path).exists(): raise ValueError("Review already exists")
    data=api(f"repos/{repo}/contents/{path}?ref={sha}")
    if data["size"]>500000 or data["encoding"]!="base64": raise ValueError("Invalid review content")
    review=strict_review(json.loads(base64.b64decode(data["content"])))
    radar.validate_review(raw,review)
    print("Review structurally validated; factual source claims still require pilot audit.")
    if os.environ.get("DRY_RUN")=="true": return
    current=api(f"repos/{repo}/branches/main")["commit"]["sha"]
    if current!=os.environ["TRUSTED_MAIN_SHA"]: raise ValueError("Main changed during validation; retry")
    merged=api(endpoint+"/merge","--method","PUT","-f",f"sha={sha}","-f","merge_method=squash","-f","commit_title=Accept validated institutional review")
    if not merged.get("merged"): raise ValueError("Merge rejected")
    print("Review merged.")
if __name__=="__main__": main()
