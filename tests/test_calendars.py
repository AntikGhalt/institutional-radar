import datetime as dt
import unittest
from src import calendars as c

class CalendarTests(unittest.TestCase):
    def test_ical(self):
        text="BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261201\r\nSUMMARY:Labour cost\\, index\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nDTSTART:20261202T233000Z\r\nSUMMARY:GDP\r\nEND:VEVENT\r\nEND:VCALENDAR"
        rows=c.parse_ics(text,"Eurostat","https://ec.europa.eu/eurostat/news/release-calendar")
        self.assertEqual(rows[0]["title"],"Labour cost, index")
        self.assertEqual(rows[1]["date"],"2026-12-03")
    def test_bad_ical(self):
        with self.assertRaises(ValueError): c.parse_ics("<html>blocked</html>","ISTAT","https://istat.it/")
    def test_ical_cancelled(self):
        self.assertEqual(c.parse_ics("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261201\nSUMMARY:X\nSTATUS:CANCELLED\nEND:VEVENT\nEND:VCALENDAR","ISTAT","https://istat.it/"),[])
    def test_inps(self):
        page="<h3>DICEMBRE 2026</h3><table><tr><td>Osservatorio</td><td>2025</td><td>Martedì - 15</td><td><a href='/x'>Link</a></td></tr></table>"
        row=c.inps_rows(page,"https://inps.it/")[0]
        self.assertEqual(row["date"],"2026-12-15")
        self.assertEqual(row["title"],"Osservatorio – 2025")
    def test_inps_bad_weekday(self):
        with self.assertRaises(ValueError): c.inps_rows("<h3>DICEMBRE 2026</h3><tr><td>X</td><td>2025</td><td>Lunedì - 15</td></tr>","https://inps.it/")
    def test_sisco(self):
        row=c.sisco_rows("III trimestre 2026   Nota sulle Comunicazioni Obbligatorie III trimestre 2026   7 dicembre 2026\n Rapporto Immigrati 2026 - MLPS   giugno 2026","https://lavoro.gov.it/")[0]
        self.assertEqual(row["date"],"2026-12-07")
        self.assertEqual(row["title"],"Nota sulle Comunicazioni Obbligatorie III trimestre 2026")
    def test_bank(self):
        html="<ol><li><span>10</span><span>Dicembre</span><span>Pubblicazioni</span><p>L'economia italiana in breve</p><span>Roma</span></li></ol>"
        rows=c.bank_rows(html,"https://bancaditalia.it/",2026,12)
        self.assertEqual(rows[0]["date"],"2026-12-10")
        self.assertEqual(rows[0]["title"],"L'economia italiana in breve")
    def test_date_filter(self):
        rows=[{"institution":"X","title":"A","date":"2026-12-01"},{"institution":"X","title":"A","date":"2026-12-01"},{"institution":"X","title":"A","date":"2027-01-01"}]
        self.assertEqual(len(c.within(rows,dt.date(2026,12,1),dt.date(2026,12,31))),1)
    def test_host(self):
        self.assertFalse(c.approved("https://inps.it.fake.example/","inps.it".split()))
        self.assertTrue(c.approved("https://www.inps.it/","inps.it".split()))
