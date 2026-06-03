import json

from app.services.result_logger import log_result


def test_writes_response_and_tools_lines(tmp_path):
    trace = json.dumps([{"step": 0, "action": "sql", "arg": {"query": "SELECT 1"}}])
    log_result(str(tmp_path), "id1", "ราคา?", "42900", 113, trace)

    response = json.loads((tmp_path / "responses.jsonl").read_text().strip())
    tools = json.loads((tmp_path / "tools.jsonl").read_text().strip())

    assert response["id"] == "id1"
    assert response["answer"] == "42900"
    assert response["total_output_token_count"] == 113
    assert tools["id"] == "id1"
    assert tools["trace"][0]["action"] == "sql"


def test_appends_one_line_per_call(tmp_path):
    log_result(str(tmp_path), "a", "q", "x", 1, "[]")
    log_result(str(tmp_path), "b", "q", "y", 2, "[]")

    lines = (tmp_path / "responses.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[1])["id"] == "b"


def test_malformed_trace_is_preserved(tmp_path):
    log_result(str(tmp_path), "id2", "q", "ans", 5, "not-json")
    tools = json.loads((tmp_path / "tools.jsonl").read_text().strip())
    assert tools["trace"] == "not-json"
