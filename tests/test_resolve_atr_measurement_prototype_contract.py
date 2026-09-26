import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

SPEC = importlib.util.spec_from_file_location(
    "atr_contract", Path(__file__).resolve().parents[1]
    / "scripts/resolve_atr_measurement_prototype_contract.py"
)
ATR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ATR)


class ContractProbeTests(unittest.TestCase):
    def test_fixed_phase_a_has_success_failure_and_ten_keys(self):
        _, summary = ATR.fixed_sample()
        selected = ATR.phase_a_sample(summary)
        self.assertEqual(len(selected), 10)
        self.assertEqual(selected.status.value_counts().to_dict(), {"SUCCESS": 5, "FAILED": 5})
        self.assertFalse(selected.duplicated(["stock_code", "year"]).any())
        pd.testing.assert_frame_equal(selected, ATR.phase_a_sample(summary))

    def test_failures_retained_and_retry_budget_survives_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            with patch.object(ATR, "OUT", out), patch.object(ATR, "REQUEST_LOG", out / "log.jsonl"), \
                    patch.object(ATR.time, "sleep"):
                session = Mock()
                session.request.side_effect = requests.ReadTimeout("test")
                for _ in range(2):
                    with self.assertRaises(RuntimeError):
                        ATR.fetch(session, "bounded", "https://example.com")
                self.assertEqual(session.request.call_count, 2)
                self.assertEqual([r["attempt_count"] for r in ATR.attempts()], [1, 2])

    def test_cache_prevents_network(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / "cache").mkdir()
            (out / "cache/test.bin").write_bytes(b"cached")
            with patch.object(ATR, "OUT", out):
                session = Mock()
                self.assertEqual(ATR.fetch(session, "test", "https://example.com"), b"cached")
                session.request.assert_not_called()

    def test_cross_stock_and_date_validation(self):
        item = dict(secCode="000001", announcementTime=0, announcementTitle="test")
        with self.assertRaises(ValueError):
            ATR.normalize_announcements([item], "000002", 2020, 1, 1)
        with self.assertRaises(ValueError):
            ATR.normalize_announcements([item], "000001", 2020, 1, 1)


if __name__ == "__main__":
    unittest.main()
