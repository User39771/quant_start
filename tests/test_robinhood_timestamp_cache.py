import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_robinhood_five_token_panel as collector  # noqa: E402
from robinhood_timestamp_cache import (  # noqa: E402
    TimestampConflictError,
    insert_exact_timestamps,
    lookup_timestamps,
)


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return [
            {
                "id": item["id"],
                "result": {"timestamp": hex(1_800_000_000 + int(item["params"][0], 16))},
            }
            for item in self.payload
        ]


class Session:
    def __init__(self):
        self.payloads = []

    def post(self, _url, *, json, **_kwargs):
        self.payloads.append(json)
        return Response(json)


class TimestampCacheTests(unittest.TestCase):
    def test_frozen_date_selection_preserves_requested_order_and_skips_completed(self):
        pending = [
            ("COST", {"market_open_date": "2026-08-24"}),
            ("COST", {"market_open_date": "2026-09-01"}),
        ]
        selected = collector.select_pending_sessions(
            pending,
            ["2026-09-01", "2026-08-19", "2026-08-24"],
            5,
        )
        self.assertEqual([item["market_open_date"] for _, item in selected], ["2026-09-01", "2026-08-24"])

    def test_tsla_research_eligibility_keeps_pre_activity_history_out_of_panel(self):
        self.assertFalse(collector.research_eligible("TSLA", {"market_open_date": "2026-07-20"}))
        self.assertTrue(collector.research_eligible("TSLA", {"market_open_date": "2026-07-21"}))
        self.assertTrue(collector.research_eligible("COST", {"market_open_date": "2026-07-20"}))

    def test_exact_insert_is_idempotent_and_conflicts_hard_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "cache.sqlite3"
            self.assertEqual(insert_exact_timestamps(database, {1: 100, 2: 200}), (2, 0))
            self.assertEqual(insert_exact_timestamps(database, {1: 100, 2: 200}), (0, 2))
            self.assertEqual(lookup_timestamps(database, [2, 3, 1]), {1: 100, 2: 200})
            with self.assertRaises(TimestampConflictError):
                insert_exact_timestamps(database, {2: 201})
            self.assertEqual(lookup_timestamps(database, [2]), {2: 200})

    def test_session_then_global_then_serial_rpc(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            database = base / "global.sqlite3"
            session_path = base / "session.json"
            session_path.write_text(json.dumps({"1": 11}), encoding="utf-8")
            insert_exact_timestamps(database, {2: 22})
            fake = Session()
            with (
                patch.object(collector, "GLOBAL_TIMESTAMP_CACHE", database),
                patch.object(collector.requests, "Session", return_value=fake),
                patch.object(collector.time, "sleep", side_effect=AssertionError("unexpected pacing")),
            ):
                values, stats = collector.batch_timestamps(list(range(1, 204)), session_path)
            self.assertEqual(values[1], 11)
            self.assertEqual(values[2], 22)
            self.assertEqual([len(payload) for payload in fake.payloads], [100, 100, 1])
            self.assertTrue(all(item["method"] == "eth_getBlockByNumber" for payload in fake.payloads for item in payload))
            self.assertEqual(stats["timestamps_reused_from_session_checkpoint"], 1)
            self.assertEqual(stats["timestamps_reused_from_global_cache"], 1)
            self.assertEqual(stats["timestamp_rpc_batch_requests"], 3)


if __name__ == "__main__":
    unittest.main()
