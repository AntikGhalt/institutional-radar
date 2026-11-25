import datetime as dt
import tempfile,unittest
from pathlib import Path
from openpyxl import load_workbook
from src.common import write
from src.digest import key,weekly_health,full_rows
from src.history import compare,stable_uid
from src.metrics import contributions
from src.spreadsheet import write_xlsx
from src import calendars as c
from src.validation import strict_review

FIX=Path(__file__).parent/"fixtures"
def event(title,date,**kw):
    return {"institution":"ISTAT","title":title,"date":date,"url":"https://www.istat.it/","relevance":"high","certainty":"confirmed","why":"Useful","evidence":"Date",**kw}
class RegressionTests(unittest.TestCase):
    def baseline(self,p,events):
        write(p/"2026-11-29"/"delivery.json",{"status":"sent"})
        write(p/"2026-11-29"/"digest-events.json",{"run_date":"2026-11-29","events":events})
    def test_change_requires_evidence_and_reuses_uid(self):
        old=event("GDP","2026-12-10",uid="a"*32); new=event("GDP","2026-12-12")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.baseline(p,[old])
            _,flags,uids,notices=compare(p,"2026-12-06",[new],{"events":[new]},True)
            self.assertEqual(flags[key(new)],"date_changed_unverified"); self.assertNotEqual(uids[key(new)],old["uid"])
            change={"institution":"ISTAT","title":"GDP","previous_date":old["date"],"kind":"rescheduled","new_date":new["date"],"url":new["url"],"evidence":"Official postponement notice"}
            _,flags,uids,notices=compare(p,"2026-12-06",[new],{"events":[new],"changes":[change]},True)
            self.assertEqual(flags[key(new)],"postponed"); self.assertEqual(uids[key(new)],old["uid"])
            self.assertEqual(notices[0]["status"],"postponed")
            rows=full_rows({"events":[old],"mode":"live"},{"events":[new]},True,lambda u,n:True,notices=notices)
            self.assertNotIn("google",rows[0])
    def test_no_automatic_cancellation(self):
        old=event("GDP","2026-12-10")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); self.baseline(p,[old])
            self.assertEqual(compare(p,"2026-12-06",[],{"events":[]},True)[3],[])
            change={"institution":"ISTAT","title":"GDP","previous_date":old["date"],"kind":"cancelled","new_date":"-","url":old["url"],"evidence":"Official cancellation"}
            self.assertEqual(compare(p,"2026-12-06",[],{"events":[],"changes":[change]},False)[3],[])
            self.assertEqual(compare(p,"2026-12-06",[],{"events":[],"changes":[change]},True)[3][0]["status"],"cancelled")
    def test_uid_repeated_title(self):
        self.assertNotEqual(stable_uid(event("Same","2026-12-09")),stable_uid(event("Same","2026-12-10")))
    def test_metrics_and_unknowns(self):
        a,b,d=event("A","2026-12-10"),event("B","2026-12-11"),event("D","2026-12-12")
        raw={"events":[a,a]}; m=contributions(raw,{"events":[a,b]},{"events":[a,d]},True,"sha")
        self.assertEqual((m["python_candidates"],m["claude_selected"],m["claude_new_vs_python"],m["audit_added_selected"],m["audit_removed_selected"],m["final_selected"]),(1,2,1,1,1,2))
        self.assertIsNone(contributions(raw,None,{"events":[a]},True)["audit_added_selected"])
        self.assertIsNone(contributions(raw,{"events":[a]},{"events":[a]},False)["audit_added_selected"])
    def test_quality_not_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            h=weekly_health(p,"2026-11-29",{"parser_quality":("partial","blocked"),"claude":("ok","done")})
            write(p/"2026-11-29"/"health.json",h)
            h=weekly_health(p,"2026-12-06",{"parser_quality":("partial","blocked"),"claude":("ok","done")})
            self.assertFalse(h["critical"]); self.assertFalse(h["degraded"])
    def test_native_excel_safe_links_and_dates(self):
        e=event("=UNSAFE()","2026-12-10")
        rows=full_rows({"events":[],"mode":"live"},{"events":[e]},True,lambda u,n:True)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"calendar.xlsx"; write_xlsx(p,rows,[],{"python_candidates":0,"final_selected":1})
            w=load_workbook(p); self.assertEqual(w.sheetnames,["Calendario","Variazioni","Metriche"])
            s=w["Calendario"]; headers={cell.value:cell.column for cell in s[1]}
            self.assertEqual(s.cell(2,headers["Titolo"]).data_type,"s")
            self.assertEqual(s.cell(2,headers["Data"]).value.date(),dt.date(2026,12,10))
            self.assertEqual(s.cell(2,headers["Fonte ufficiale"]).hyperlink.target,e["url"])
            self.assertTrue(s.cell(2,headers["Google Calendar"]).hyperlink.target.startswith("https://"))
            self.assertEqual(s.cell(2,headers["Rilevanza"]).value,"Alta")
            w.close()
    def test_captured_formats(self):
        read=lambda name:(FIX/name).read_text(encoding="utf-8")
        self.assertEqual(c.parse_ics(read("istat.ics"),"ISTAT","https://istat.it/")[0]["date"],"2018-02-27")
        self.assertEqual(c.parse_ics(read("eurostat.ics"),"Eurostat","https://ec.europa.eu/eurostat/")[0]["date"],"2026-11-30")
        self.assertEqual(c.inps_rows(read("inps.html"),"https://inps.it/")[0]["date"],"2026-01-21")
        self.assertEqual(c.sisco_rows(read("sisco-2026.txt"),"https://lavoro.gov.it/")[0]["date"],"2026-03-09")
        self.assertEqual(c.bank_rows(read("bank-2026-12.html"),"https://bancaditalia.it/",2026,12)[0]["date"],"2026-12-01")
