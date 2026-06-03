"""Append per-request results to two JSONL logs under a logs directory.

responses.jsonl  -- the response body returned to the caller
tools.jsonl      -- the tool/action calls the agent made to reach the answer
"""
import json
import time
from pathlib import Path


def _append_jsonl(path: Path, record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def log_result(
    log_dir: str,
    request_id: str,
    question: str,
    answer: str,
    total_output_token_count: int,
    trace_json: str,
) -> None:
    """Append one line to responses.jsonl and one to tools.jsonl."""
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    _append_jsonl(directory / "responses.jsonl", {
        "ts": ts,
        "id": request_id,
        "question": question,
        "answer": answer,
        "total_output_token_count": total_output_token_count,
    })

    try:
        trace = json.loads(trace_json) if trace_json else []
    except (ValueError, TypeError):
        trace = trace_json
    _append_jsonl(directory / "tools.jsonl", {
        "ts": ts,
        "id": request_id,
        "question": question,
        "trace": trace,
    })
