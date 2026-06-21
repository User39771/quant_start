from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

import pandas as pd


class AkShareDiagnosticScriptTests(unittest.TestCase):
    def test_run_diagnostics_reports_versions_and_success_rate(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_akshare_connection.py"
        spec = importlib.util.spec_from_file_location("check_akshare_connection", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        ak_module = types.SimpleNamespace(__version__="1.0.0")
        requests_module = types.SimpleNamespace(__version__="2.0.0")
        calls = {"count": 0}

        def fetcher():
            calls["count"] += 1
            if calls["count"] in {2, 4}:
                raise TimeoutError("timeout")
            return pd.DataFrame({"code": ["600519"]})

        result = module.run_diagnostics(
            ak_module=ak_module,
            requests_module=requests_module,
            fetcher=fetcher,
            repeats=5,
            repeat_sleep_seconds=0,
        )

        self.assertEqual(result["python_executable"], sys.executable)
        self.assertEqual(result["akshare_version"], "1.0.0")
        self.assertEqual(result["requests_version"], "2.0.0")
        self.assertTrue(result["single_request_ok"])
        self.assertEqual(result["success_count"], 3)
        self.assertEqual(result["total_count"], 5)
        self.assertEqual(result["success_rate"], 0.6)


if __name__ == "__main__":
    unittest.main()
