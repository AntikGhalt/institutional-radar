"""One-click draft events; no account access or automatic insertion."""
import datetime as dt
from urllib.parse import urlencode,quote

def calendar_links(event,verified=False):
    day=dt.date.fromisoformat(event["date"]); end=day+dt.timedelta(days=1)
    title=event["institution"]+" — "+event["title"]
    if not verified: title="[Da verificare] "+title
    details=event.get("why") or event.get("status") or ""
    details=(details+"\n"+event["url"]).strip()
    google="https://calendar.google.com/calendar/r/eventedit?"+urlencode({"action":"TEMPLATE","text":title,"dates":day.strftime("%Y%m%d")+"/"+end.strftime("%Y%m%d"),"details":details},quote_via=quote)
    outlook="https://outlook.office.com/calendar/0/deeplink/compose?"+urlencode({"path":"/calendar/action/compose","rru":"addevent","subject":title,"startdt":day.isoformat(),"enddt":end.isoformat(),"allday":"true","body":details},quote_via=quote)
    return {"google":google,"outlook":outlook}

def individual_ics_url(run_date,uid):
    # Public, official-source-only calendar artifacts. Published before SMTP.
    return f"https://github.com/AntikGhalt/institutional-radar/raw/refs/heads/main/data/{run_date}/calendar-events/{uid}.ics"
