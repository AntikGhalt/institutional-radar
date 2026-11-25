"""Conservative, reproducible contribution measures, never inferred credit."""
from src.digest import key
def selections(review):
    return {key(e):e for e in (review or {}).get("events",[]) if e["relevance"]!="calendar_only"}

def contributions(raw,original,final,audited,baseline=None):
    python={key(e) for e in raw.get("events",[])}
    c=selections(original); f=selections(final)
    known=original is not None
    compare=known and audited
    return {"python_candidates":len(python),"claude_selected":len(c) if known else None,
            "claude_new_vs_python":len(c.keys()-python) if known else None,
            "audit_added_selected":len(f.keys()-c.keys()) if compare else None,
            "audit_removed_selected":len(c.keys()-f.keys()) if compare else None,
            "audit_changed_fields":sum(c[k]!=f[k] for k in c.keys() & f.keys()) if compare else None,
            "final_selected":len(f),"claude_baseline":baseline,
            "method":"Exact normalized institution/date/title matches. A changed title/date can count as an addition and removal. Counts measure recorded differences, not correctness or causal contributions."}
