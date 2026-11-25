import unittest
from src.accept_review import check_pr, strict_review
class AcceptTests(unittest.TestCase):
    def setUp(self):
        self.repo="owner/radar"
        self.pr={"state":"open","draft":False,"base":{"ref":"main"},"head":{"repo":{"full_name":self.repo},"ref":"claude/test","sha":"abc"},"user":{"login":"owner"},"changed_files":1}
        self.files=[{"filename":"data/2026-11-29/review.json","status":"added"}]
    def check(self): return check_pr(self.pr,self.repo,"owner",self.files)
    def test_valid(self): self.assertEqual(self.check()[0],self.files[0]["filename"])
    def test_fork(self):
        self.pr["head"]["repo"]["full_name"]="other/radar"
        with self.assertRaises(ValueError): self.check()
    def test_other_author(self):
        self.pr["user"]["login"]="other"
        with self.assertRaises(ValueError): self.check()
    def test_code(self):
        self.files[0]["filename"]="src/radar.py"
        with self.assertRaises(ValueError): self.check()
    def test_overwrite(self):
        self.files[0]["status"]="modified"
        with self.assertRaises(ValueError): self.check()
    def test_extra_file(self):
        self.pr["changed_files"]=2
        with self.assertRaises(ValueError): self.check()
    def test_extra_field(self):
        with self.assertRaises(ValueError): strict_review({"unexpected":"field"})
