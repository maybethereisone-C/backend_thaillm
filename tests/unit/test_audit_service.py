import pytest
from pathlib import Path

from app.services.audit_service import write_audit_trail


def test_write_audit_trail_creates_file(tmp_path):
    write_audit_trail("abc-123", "trace content", str(tmp_path / "audits"))
    assert (tmp_path / "audits" / "abc-123.txt").read_text() == "trace content"


def test_write_audit_trail_creates_missing_dir(tmp_path):
    target = tmp_path / "deep" / "nested" / "dir"
    write_audit_trail("xyz", "data", str(target))
    assert (target / "xyz.txt").exists()


def test_write_audit_trail_overwrites_existing(tmp_path):
    write_audit_trail("dup", "first", str(tmp_path))
    write_audit_trail("dup", "second", str(tmp_path))
    assert (tmp_path / "dup.txt").read_text() == "second"
