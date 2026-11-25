import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from src import radar as r
class RadarTests(unittest.TestCase):
    def setUp(self):
        self.raw={"schema":1,"mode":"demo","run_date":"2026-11-29","sources":[{"institution":s["name"],"status":"demo_not_fetched"} for s in r.SOURCES],"events":[]}
        self.review=r.make_demo_review(self.raw)
    def test_review(self): self.assertEqual(r.validate_review(self.raw,self.review),self.review)
    def test_hash(self):
        self.raw["events"]=["changed"]
        with self.assertRaises(ValueError): r.validate_review(self.raw,self.review)
    def test_coverage(self):
        self.review["coverage"].pop()
        with self.assertRaises(ValueError): r.validate_review(self.raw,self.review)
    def test_domain(self):
        self.review["events"][0]["url"]="https://istat.it.example.com/fake"
        with self.assertRaises(ValueError): r.validate_review(self.raw,self.review)
    def test_date(self):
        self.review["events"][0]["date"]="2027-01-01"
        with self.assertRaises(ValueError): r.validate_review(self.raw,self.review)
    def test_duplicate(self):
        self.review["events"].append(copy.deepcopy(self.review["events"][0]))
        with self.assertRaises(ValueError): r.validate_review(self.raw,self.review)
    def test_demo_no_calendar_no_send(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,"ROOT",Path(tmp)):
            out,title=r.render(self.raw,self.review)
            self.assertIn("DEMO",(out/"report.html").read_text())
            self.assertNotIn("BEGIN:VEVENT",(out/"calendar.ics").read_text())
            with self.assertRaises(ValueError): r.send(self.raw,self.review,out,title)
    def test_missing_review(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,"ROOT",Path(tmp)):
            self.raw["mode"]="live"; out,title=r.render(self.raw,None)
            with self.assertRaises(ValueError): r.send(self.raw,None,out,title)
    def test_live_calendar_and_html(self):
        self.raw["mode"]="live"; self.review["mode"]="live"; self.review["collection_sha256"]=r.digest(self.raw)
        self.review["events"][0]["title"]="<script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,"ROOT",Path(tmp)):
            out,_=r.render(self.raw,r.validate_review(self.raw,self.review),audited=True)
            self.assertIn("BEGIN:VEVENT",(out/"calendar.ics").read_text()); self.assertNotIn("<script>",(out/"report.html").read_text())
    def test_calendar_only_and_individual_links(self):
        self.raw["mode"]="live"; self.review["mode"]="live"; self.review["collection_sha256"]=r.digest(self.raw)
        self.review["events"][0]["relevance"]="calendar_only"
        self.review["events"][1]["relevance"]="medium"
        self.review["events"][2]["certainty"]="tentative"
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,"ROOT",Path(tmp)):
            out,_=r.render(self.raw,r.validate_review(self.raw,self.review),audited=True)
            page=(out/"report.html").read_text()
            self.assertNotIn("Evento sintetico 1 (NON REALE)",page)
            self.assertIn("Evento sintetico 1 (NON REALE)",(out/"full-calendar.csv").read_text())
            self.assertIn("outlook.office.com",page)
            self.assertEqual(len(list((out/"calendar-events").glob("*.ics"))),1)
            self.assertNotIn("BEGIN:VEVENT",(out/"calendar.ics").read_text())
    def test_sent_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,"ROOT",Path(tmp)),patch.dict(r.os.environ,{"ENABLE_EMAIL":"true","RADAR_DELIVERY_TOKEN":"test"}):
            self.raw["mode"]="live"
            r.write(Path(tmp)/"data"/self.raw["run_date"]/"delivery.json",{"status":"sent"})
            r.send(self.raw,None,Path(tmp),"",reserve_only=True)
            r.send(self.raw,None,Path(tmp),"")
if __name__=="__main__": unittest.main()
