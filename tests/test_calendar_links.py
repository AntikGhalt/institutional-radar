import unittest
from urllib.parse import urlsplit,parse_qs
from src.calendar_links import calendar_links
class CalendarLinkTests(unittest.TestCase):
    def test_all_day_and_encoding(self):
        e={"institution":"Eurostat","title":"Employment & wages","date":"2026-12-31","url":"https://ec.europa.eu/eurostat/news/release-calendar"}
        links=calendar_links(e,True)
        g=parse_qs(urlsplit(links["google"]).query); o=parse_qs(urlsplit(links["outlook"]).query)
        self.assertEqual(g["dates"],["20261231/20270101"])
        self.assertEqual(o["startdt"],["2026-12-31"]); self.assertEqual(o["enddt"],["2027-01-01"])
        self.assertEqual(o["allday"],["true"]); self.assertEqual(g["text"],["Eurostat — Employment & wages"])
