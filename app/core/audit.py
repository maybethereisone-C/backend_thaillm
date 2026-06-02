import logging
import sys


audit_logger = logging.getLogger("llm.audit")


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger("llm")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
