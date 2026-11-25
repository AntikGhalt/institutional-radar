import tempfile,unittest
from pathlib import Path
from src import radar
from src.history import classify
from src.digest import key

class HistoryTests(unittest.TestCase):
    def test_previous_sent_nonempty_and_exact_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            event={"institution":"ISTAT","title":"Occupati – Ottobre 2026","date":"2026-12-02"}
            same={**event,"title":"Occupati | Ottobre 2026"}
            changed={**event,"date":"2026-12-03"}
            for date,status,events in [("2026-11-22","sent",[event]),("2026-11-29","sent",[]),("2026-12-06","reserved",[changed])]:
                radar.write(p/date/"delivery.json",{"status":status})
                radar.write(p/date/"digest-events.json",{"run_date":date,"events":events})
            baseline,labels=classify(p,"2026-12-13",[same,changed])
            self.assertEqual(baseline,"2026-11-22")
            self.assertEqual(labels[key(same)],"already_reported")
            self.assertEqual(labels[key(changed)],"new")
    def test_no_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            e={"institution":"ISTAT","title":"GDP","date":"2026-12-01"}
            baseline,labels=classify(Path(tmp),"2026-11-29",[e])
            self.assertIsNone(baseline); self.assertEqual(labels[key(e)],"baseline_unavailable")
