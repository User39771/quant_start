from __future__ import annotations

import json
import hashlib
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

PROPOSAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["suggestion", "formula"],
    "properties": {
        "suggestion": {"type": "string"},
        "formula": {"type": "string"},
    },
}
LLM_PROVIDER_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    latency_seconds: float
    output: dict[str, str] | None
    error: str | None
    diagnostic: str | None = None
    task_id: str | None = None
    prompt_hash: str | None = None
    subagent_failure: str | None = None


class CodexProvider:
    """Ephemeral one-call suggestion+formula interface for both LLM arms."""

    def __init__(self, model: str = "gpt-5.6-sol", reasoning_effort: str = "medium"):
        self.model = model
        self.reasoning_effort = reasoning_effort

    def invoke(self, prompt: str, schema_path: Path, cwd: Path) -> ProviderResult:
        schema_path.write_text(json.dumps(PROPOSAL_SCHEMA), encoding="utf-8")
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--model",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "--output-schema",
            str(schema_path),
            prompt,
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=LLM_PROVIDER_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProviderResult(
                False,
                time.perf_counter() - started,
                None,
                f"provider timeout after {LLM_PROVIDER_TIMEOUT_SECONDS}s",
            )
        latency = time.perf_counter() - started
        if completed.returncode:
            error = (completed.stderr or completed.stdout).strip()
            return ProviderResult(False, latency, None, error, completed.stderr.strip() or None)
        try:
            return ProviderResult(
                True,
                latency,
                json.loads(completed.stdout),
                None,
                completed.stderr.strip() or None,
            )
        except json.JSONDecodeError as exc:
            return ProviderResult(
                False,
                latency,
                None,
                f"structured output parse failed: {exc}",
                completed.stderr.strip() or None,
            )


class NativeSubagentProvider:
    """File bridge between deterministic Python state and the native parent harness."""

    def __init__(
        self,
        bridge_dir: Path,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "medium",
        timeout_seconds: int = LLM_PROVIDER_TIMEOUT_SECONDS,
    ):
        self.bridge_dir = bridge_dir
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.bridge_dir.mkdir(parents=True, exist_ok=True)

    def invoke(
        self,
        prompt: str,
        schema_path: Path,
        cwd: Path,
        metadata: dict[str, object] | None = None,
    ) -> ProviderResult:
        del schema_path, cwd
        request_id = uuid.uuid4().hex
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        request_path = self.bridge_dir / f"{request_id}.request.json"
        response_path = self.bridge_dir / f"{request_id}.response.json"
        request_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "role": "FORMULA_GENERATOR",
                    "model": self.model,
                    "reasoning_effort": self.reasoning_effort,
                    "fork_turns": "none",
                    "prompt": prompt,
                    "prompt_hash": prompt_hash,
                    "response_contract": {"suggestion": "string", "formula": "string"},
                    "resume_metadata": metadata or {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        started = time.perf_counter()
        while time.perf_counter() - started < self.timeout_seconds:
            if response_path.exists():
                latency = time.perf_counter() - started
                try:
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                    if response.get("model") != self.model or response.get("reasoning_effort") != self.reasoning_effort:
                        raise ValueError("native subagent model/reasoning mismatch")
                    if response.get("tool_or_repository_leakage"):
                        raise ValueError("native subagent tool/repository leakage")
                    output = response["output"]
                    if set(output) != {"suggestion", "formula"} or not all(isinstance(output[key], str) for key in output):
                        raise ValueError("native subagent output schema mismatch")
                    return ProviderResult(
                        True, latency, output, None, response.get("diagnostic"),
                        response.get("task_id"), prompt_hash, None,
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    return ProviderResult(
                        False, latency, None, str(exc), None,
                        response.get("task_id") if isinstance(response, dict) else None,
                        prompt_hash, "MALFORMED_OR_LEAKING_RESPONSE",
                    )
            time.sleep(0.25)
        return ProviderResult(
            False,
            time.perf_counter() - started,
            None,
            f"native subagent timeout after {self.timeout_seconds}s",
            None,
            None,
            prompt_hash,
            "NATIVE_SUBAGENT_TIMEOUT",
        )


LAUNCH_MARKER_SCHEMA_VERSION = "alpha-jungle-c0-launch-v2"


def build_launch_marker(
    request: dict[str, object], task_id: str, timestamp_utc: str
) -> dict[str, object]:
    """Build the required schema for every new native-subagent launch marker."""
    if not timestamp_utc:
        raise ValueError("new launch markers require timestamp_utc")
    metadata = request["resume_metadata"]
    return {
        "schema_version": LAUNCH_MARKER_SCHEMA_VERSION,
        "legacy_marker": False,
        "experiment_id": metadata["experiment_id"],
        "arm": metadata["arm"],
        "proposal_id": f'{metadata["arm"]}:{metadata["proposal_index"]}',
        "charged_call_index": metadata["charged_call_index"],
        "launch_status": "launched",
        "timestamp_utc": timestamp_utc,
        "prompt_version": metadata["prompt_version"],
        "prompt_hash": metadata["generator_prompt_hash"],
        "subagent_task_id": task_id,
    }


def normalize_launch_marker(
    marker: dict[str, object], request: dict[str, object]
) -> dict[str, object]:
    """Load current markers and explicitly migrate legacy markers without inventing time."""
    metadata = request["resume_metadata"]
    if "schema_version" not in marker:
        return {
            "schema_version": LAUNCH_MARKER_SCHEMA_VERSION,
            "legacy_marker": True,
            "experiment_id": metadata.get("experiment_id", "ALPHA_JUNGLE_QLIB_C0"),
            "arm": metadata["arm"],
            "proposal_id": f'{metadata["arm"]}:{metadata["proposal_index"]}',
            "charged_call_index": metadata["charged_call_index"],
            "launch_status": "launched",
            "timestamp_utc": None,
            "prompt_version": metadata["prompt_version"],
            "prompt_hash": metadata["generator_prompt_hash"],
            "subagent_task_id": marker.get("subagent_task_id", marker.get("task_id")),
        }
    required = {
        "schema_version", "experiment_id", "arm", "proposal_id",
        "charged_call_index", "launch_status", "timestamp_utc", "prompt_version",
        "prompt_hash", "subagent_task_id",
    }
    missing = required - marker.keys()
    if missing or marker["timestamp_utc"] is None:
        raise ValueError(f"invalid current launch marker; missing={sorted(missing)}")
    return {**marker, "legacy_marker": bool(marker.get("legacy_marker", False))}
