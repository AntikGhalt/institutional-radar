"""Capture bounded, public calendar-format excerpts for regression review.

Only selected public calendar fields are retained; no response headers, cookies,
scripts, contact details, or full pages are stored.
"""
import re
from src.calendars import clean,parse_html,parse_ics,inps_rows,sisco_rows,bank_rows,month_year
from xml.sax.saxutils import escape

def ical_excerpt(text):
    unfolded=re.sub(r"\r?\n[ \t]","",text)
    blocks=[]
    for body in re.findall(r"(?ms)^BEGIN:VEVENT\r?\n(.*?)^END:VEVENT",unfolded):
        lines=[x for x in body.splitlines() if x.split(":",1)[0].split(";",1)[0] in ("DTSTART","SUMMARY","STATUS","RRULE")]
        if not any(x.startswith("DTSTART") for x in lines) or not any(x.startswith("SUMMARY") for x in lines): continue
        if any(x.startswith("RRULE") for x in lines): continue
        blocks.extend(["BEGIN:VEVENT",*lines,"END:VEVENT"])
        if blocks: break
    if not blocks: return None
    return "\r\n".join(["BEGIN:VCALENDAR","VERSION:2.0",*blocks,"END:VCALENDAR",""])

def table_excerpt(text,source):
    current=None
    for tag,txt,cells,_ in parse_html(text).blocks:
        if month_year(txt): current=txt
        if tag=="tr" and current and len(cells)>=3 and re.fullmatch(r"[A-Za-zÀ-ÿ]+\s*[-–]\s*\d{1,2}",cells[2]):
            fragment="<h3>"+escape(current)+"</h3><table><tr>"+"".join("<td>"+escape(v)+"</td>" for v in cells[:3])+"</tr></table>"
            inps_rows(fragment,source); return fragment
    return None

def agenda_excerpt(text,source,year,month):
    # Retain just the public date/category/title text nodes in a minimal fragment.
    for tag,txt,cells,parts in parse_html(text).blocks:
        if tag!="li": continue
        fragment="<li>"+"".join("<span>"+escape(p)+"</span>" for p in parts)+"</li>"
        try: bank_rows(fragment,source,year,month); return "<ol>"+fragment+"</ol>"
        except ValueError: continue
    return None

def sisco_excerpt(text,source):
    for line in text.splitlines():
        try: sisco_rows(line,source); return line+"\n"
        except ValueError: continue
    return None
