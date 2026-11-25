"""Read trusted data-only Claude handoffs without executing PR code."""
import base64,json,os
from src.accept_review import api,check_pr
from src.validation import validate_review

def read_candidate(repo,path,sha,raw):
    file=api(f"repos/{repo}/contents/{path}?ref={sha}")
    if file.get("encoding")!="base64" or file.get("size",0)>1_000_000: raise ValueError("Invalid review blob")
    return validate_review(raw,json.loads(base64.b64decode(file["content"])))

def baseline(repo,endpoint,path,raw,preferred):
    try:
        commits=api(endpoint+"/commits?per_page=100")
        shas=[c["sha"] for c in commits]
        if not shas: return None,None
        if preferred:
            if preferred not in shas: return None,None
            return read_candidate(repo,path,preferred,raw),"Exact pre-audit Claude head: "+preferred
        return read_candidate(repo,path,shas[0],raw),"First PR commit (legacy/estimate): "+shas[0]
    except Exception: return None,None

def find_review(raw,validate,main_review,preferred=None):
    repo=os.getenv("GITHUB_REPOSITORY"); owner=os.getenv("GITHUB_REPOSITORY_OWNER")
    if not repo or not owner or not os.getenv("GH_TOKEN"):
        return main_review,"unknown","Provenienza Claude non verificabile in questa esecuzione.",None,None
    path="data/"+raw["run_date"]+"/review.json"
    try:
        # Restrict the scan to recent PRs; fetch details only for matching owner branches.
        prs=api(f"repos/{repo}/pulls?state=all&sort=created&direction=desc&per_page=100")
    except Exception:
        return main_review,"unknown","Impossibile verificare le PR tramite GitHub.",None,None
    invalid=False
    for p in prs:
        head=p.get("head",{})
        if p.get("user",{}).get("login")!=owner or (head.get("repo") or {}).get("full_name")!=repo or not head.get("ref","").startswith("claude/") or p.get("base",{}).get("ref")!="main": continue
        endpoint=f"repos/{repo}/pulls/{int(p['number'])}"
        try:
            files=api(endpoint+"/files?per_page=2")
            if not any(f.get("filename")==path for f in files): continue
            pr=api(endpoint)
            if pr.get("changed_files")!=1 or len(files)!=1 or files[0].get("status")!="added": invalid=True; continue
            if not pr.get("merged") and pr.get("state")!="open": continue
            if pr.get("state")=="open": check_pr(pr,repo,owner,files)
            candidate=read_candidate(repo,path,pr["head"]["sha"],raw)
            original,origin=baseline(repo,endpoint,path,raw,preferred)
            return main_review if main_review is not None else candidate,"ok",f"PR Claude #{int(p['number'])} validata.",original,origin
        except Exception: invalid=True; continue
    return main_review,"invalid" if invalid else "missing","Consegna Claude non valida o non disponibile.",None,None
