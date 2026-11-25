"""Read trusted data-only Claude handoffs without executing PR code."""
import base64
import json
import os
from src.accept_review import api, check_pr, strict_review

def find_review(raw, validate, main_review):
    repo=os.getenv("GITHUB_REPOSITORY"); owner=os.getenv("GITHUB_REPOSITORY_OWNER")
    if not repo or not owner or not os.getenv("GH_TOKEN"):
        return main_review, "unknown", "Provenienza Claude non verificabile in questa esecuzione."
    path="data/"+raw["run_date"]+"/review.json"
    try:
        prs=api(f"repos/{repo}/pulls?state=all&sort=created&direction=desc&per_page=100")
        for p in prs:
            head=p.get("head",{})
            if p.get("user",{}).get("login")!=owner or (head.get("repo") or {}).get("full_name")!=repo or not head.get("ref","").startswith("claude/") or p.get("base",{}).get("ref")!="main": continue
            if p.get("state")!="open" and not p.get("merged_at"): continue
            endpoint=f"repos/{repo}/pulls/{int(p['number'])}"
            files=api(endpoint+"/files?per_page=2")
            if len(files)!=1 or files[0].get("filename")!=path or files[0].get("status")!="added": continue
            pr=api(endpoint)
            if pr.get("merged") and main_review is not None and pr.get("changed_files")==1:
                return main_review,"ok",f"PR Claude #{int(p['number'])} integrata."
            if p.get("state")!="open": continue
            _,_,sha=check_pr(pr,repo,owner,files)
            file=api(f"repos/{repo}/contents/{path}?ref={sha}")
            if file.get("encoding")!="base64" or file.get("size",0)>500000: continue
            candidate=strict_review(json.loads(base64.b64decode(file["content"])))
            validate(raw,candidate)
            return main_review if main_review is not None else candidate,"ok",f"PR Claude #{int(p['number'])} valida; eventuale audit separato."
        return main_review,"missing","Nessuna consegna Claude valida rilevata per questa settimana."
    except Exception:
        return main_review,"unknown","Impossibile verificare la consegna Claude tramite GitHub."
