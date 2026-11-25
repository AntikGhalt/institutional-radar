import tempfile,unittest
from pathlib import Path
from src.audit import blob_sha,validate_audit
class AuditTests(unittest.TestCase):
    def test_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/"collection.json").write_text("{}"); (p/"review.json").write_text("{}")
            raw={"mode":"live","run_date":"2026-11-29"}
            a={"schema":1,"run_date":raw["run_date"],"collection_blob_sha":blob_sha(p/"collection.json"),"review_blob_sha":blob_sha(p/"review.json"),"status":"approved","auditor":"ChatGPT","summary":"test","limitations":"test"}
            self.assertEqual(validate_audit(p,raw,{},a),a)
            (p/"review.json").write_text("{ }")
            with self.assertRaises(ValueError): validate_audit(p,raw,{},a)
    def test_demo(self):
        with self.assertRaises(ValueError): validate_audit(Path("."),{"mode":"demo"},{},{})
