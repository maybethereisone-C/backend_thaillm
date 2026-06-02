from pathlib import Path


def write_audit_trail(request_id: str, content: str, audit_dir: str) -> None:
    Path(audit_dir).mkdir(parents=True, exist_ok=True)
    Path(audit_dir, f"{request_id}.txt").write_text(content, encoding="utf-8")
