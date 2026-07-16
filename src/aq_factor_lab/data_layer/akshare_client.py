from __future__ import annotations

import json
import re
import subprocess
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

try:
    import akshare as ak
except Exception:  # pragma: no cover - optional runtime dependency
    ak = None


class AkSharePublicClient:
    """Thin wrapper around AkShare endpoints used by the public data layer."""

    _EASTMONEY_CLIST_URL = "http://push2.eastmoney.com/api/qt/clist/get"
    _EASTMONEY_HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/center/boardlist.html",
    }

    @property
    def version(self) -> str:
        return str(getattr(ak, "__version__", "unknown")) if ak is not None else "unavailable"

    def _require_akshare(self) -> Any:
        if ak is None:
            raise RuntimeError("AkShare is not installed. Install requirements.txt first.")
        return ak

    def stock_daily(self, symbol: str, start: str, end: str, adjusted: bool, timeout: float) -> pd.DataFrame:
        module = self._require_akshare()
        return module.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq" if adjusted else "",
            timeout=int(timeout),
        )

    def index_daily(self, index_code: str, start: str, end: str, timeout: float) -> pd.DataFrame:
        module = self._require_akshare()
        return module.index_zh_a_hist(
            symbol=index_code,
            period="daily",
            start_date=start,
            end_date=end,
        )

    def stock_universe(self) -> pd.DataFrame:
        module = self._require_akshare()
        return module.stock_zh_a_spot_em()

    def concept_names(self) -> pd.DataFrame:
        module = self._require_akshare()
        try:
            return module.stock_board_concept_name_em()
        except Exception:
            raw = self._eastmoney_clist(
                fs="m:90 t:3 f:!50",
                fields="f12,f14",
            )
            return raw.rename(columns={"f12": "板块代码", "f14": "板块名称"})[
                ["板块代码", "板块名称"]
            ]

    def concept_members(self, concept_name: str) -> pd.DataFrame:
        module = self._require_akshare()
        if re.match(r"^BK\d+", concept_name):
            return self._concept_members_by_code(concept_name)
        try:
            return module.stock_board_concept_cons_em(symbol=concept_name)
        except Exception:
            return self._concept_members_by_code(self._concept_code(concept_name))

    def _concept_members_by_code(self, concept_code: str) -> pd.DataFrame:
        raw = self._eastmoney_clist(
            fs=f"b:{concept_code} f:!50",
            fields="f12,f14",
        )
        return raw.rename(columns={"f12": "code", "f14": "name"})[["code", "name"]]

    def _concept_code(self, concept_name: str) -> str:
        concepts = self.concept_names()
        name_col = "板块名称" if "板块名称" in concepts.columns else "concept_name"
        code_col = "板块代码" if "板块代码" in concepts.columns else "concept_code"
        matches = concepts.loc[concepts[name_col].astype(str) == concept_name, code_col]
        if matches.empty:
            raise ValueError(f"Cannot resolve AkShare concept code for {concept_name}")
        return str(matches.iloc[0])

    def _eastmoney_clist(self, *, fs: str, fields: str, timeout: float = 20.0) -> pd.DataFrame:
        session = requests.Session()
        session.trust_env = False
        rows: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        total = 0
        while True:
            params = {
                "pn": str(page),
                "pz": str(page_size),
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f12",
                "fs": fs,
                "fields": fields,
            }
            payload = self._eastmoney_payload(session, params, timeout)
            if payload.get("rc") != 0:
                raise RuntimeError(f"Eastmoney clist returned rc={payload.get('rc')}")
            data = payload.get("data") or {}
            diff = data.get("diff") or []
            rows.extend(diff)
            total = int(data.get("total") or len(rows))
            if not diff or len(rows) >= total:
                break
            page += 1
        return pd.DataFrame(rows)

    def _eastmoney_payload(
        self,
        session: requests.Session,
        params: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        try:
            response = session.get(
                self._EASTMONEY_CLIST_URL,
                params=params,
                headers=self._EASTMONEY_HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            url = f"{self._EASTMONEY_CLIST_URL}?{urlencode(params)}"
            return json.loads(self._powershell_get_text(url, timeout))

    def _powershell_get_text(self, url: str, timeout: float) -> str:
        escaped_url = url.replace("'", "''")
        timeout_seconds = max(1, int(timeout))
        command = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            "$ProgressPreference='SilentlyContinue'; "
            f"$r = Invoke-WebRequest -Uri '{escaped_url}' -UseBasicParsing "
            f"-TimeoutSec {timeout_seconds} "
            "-Headers @{ 'User-Agent'='Mozilla/5.0'; "
            "'Referer'='https://quote.eastmoney.com/center/boardlist.html' }; "
            "Write-Output $r.Content"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=timeout + 5,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "PowerShell Eastmoney request failed")
        return completed.stdout
