import tempfile,unittest
from pathlib import Path
from src.digest import weekly_health,full_rows,cell
from src import radar
class DigestTests(unittest.TestCase):
    def test_two_weeks_critical_and_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            one=weekly_health(p,"2026-11-29",{"claude":("missing","none"),"chatgpt":("ok","done")})
            self.assertTrue(one["degraded"]); self.assertFalse(one["critical"])
            radar.write(p/"2026-11-29"/"health.json",one)
            two=weekly_health(p,"2026-12-06",{"claude":("unknown","none"),"chatgpt":("ok","done")})
            self.assertTrue(two["critical"]); self.assertEqual(two["stages"]["claude"]["missed_weeks"],2)
            radar.write(p/"2026-12-06"/"health.json",two)
            three=weekly_health(p,"2026-12-13",{"claude":("ok","done"),"chatgpt":("ok","done")})
            self.assertFalse(three["degraded"])
    def test_raw_and_review_labels(self):
        e={"institution":"ISTAT","date":"2026-12-01","title":"GDP","url":"https://istat.it/","evidence":"calendar","certainty":"confirmed"}
        rows=full_rows({"events":[e]},None,False,lambda u,n:True)
        self.assertEqual(rows[0]["selected"],"No"); self.assertIn("non verificato",rows[0]["status"])
        rows=full_rows({"events":[e]},{"events":[e]},False,lambda u,n:True)
        self.assertEqual(len(rows),1); self.assertIn("audit indipendente assente",rows[0]["status"])
    def test_csv_safe(self):
        self.assertEqual(cell("=1+1"),"'=1+1")
