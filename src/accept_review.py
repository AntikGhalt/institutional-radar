"""Validate owner-authored, same-repository review-data PRs.

Never check out or execute pull request code. GitHub's API supplies JSON data.
"""
import base64
import datetime as dt
import json
import os
import re
import subprocess
from src.common import ROOT,load
from src.validation import validate_collection,validate_review,strict_review

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

def main():
    repo=os.environ["GITHUB_REPOSITORY"]; owner=os.environ["GITHUB_REPOSITORY_OWNER"]; num=int(os.environ["PR_NUMBER"])
    endpoint=f"repos/{repo}/pulls/{num}"
    pr=api(endpoint); files=api(endpoint+"/files?per_page=2")
    path,date,sha=check_pr(pr,repo,owner,files)
    raw=validate_collection(load(ROOT/"data"/str(date)/"collection.json"),date)
    if (ROOT/path).exists(): raise ValueError("Review already exists")
    data=api(f"repos/{repo}/contents/{path}?ref={sha}")
    if data["size"]>1_000_000 or data["encoding"]!="base64": raise ValueError("Invalid review content")
    review=validate_review(raw,json.loads(base64.b64decode(data["content"])))
    print(f"Validated review at {sha}: {len(review['events'])} events; no merge performed.")
if __name__=="__main__": main()
