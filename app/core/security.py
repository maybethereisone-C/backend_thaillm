import base64
import re
import secrets
from dataclasses import dataclass

from fastapi import Request

from app.core.errors import AuthenticationError, RequestPolicyError


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


class PromptInjectionGuard:
    def __init__(self) -> None:
        self._patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
                r"\breveal\s+(the\s+)?(system|developer)\s+prompt\b",
                r"\bsystem\s+(override|prompt|instructions?)\b",
                r"\byou\s+are\s+now\s+(in\s+)?developer\s+mode\b",
                r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
                r"\btool\s*call\s*override\b",
                r"\b(thought|observation)\s*:\s*.*\b(ignore|override|bypass|reveal)\b",
                r"<\s*img\b[^>]*\bsrc\s*=\s*['\"]?https?://",
            )
        ]
        self._typoglycemia_terms = {
            "ignore",
            "bypass",
            "override",
            "reveal",
            "system",
            "developer",
            "instructions",
        }

    def inspect_text(self, value: str) -> GuardResult:
        normalized = self._normalize(value)
        for pattern in self._patterns:
            if pattern.search(normalized):
                return GuardResult(False, "prompt injection pattern detected")

        words = re.findall(r"\b[a-zA-Z]{4,}\b", normalized.lower())
        for word in words:
            if any(self._is_typoglycemia_variant(word, term) for term in self._typoglycemia_terms):
                return GuardResult(False, "obfuscated prompt injection keyword detected")

        if self._contains_encoded_injection(normalized):
            return GuardResult(False, "encoded prompt injection detected")

        return GuardResult(True)

    def enforce_text(self, value: str) -> None:
        result = self.inspect_text(value)
        if not result.allowed:
            raise RequestPolicyError(result.reason or "request rejected by prompt guard")

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("\u200b", "").replace("\ufeff", "")).strip()

    def _is_typoglycemia_variant(self, word: str, target: str) -> bool:
        if word == target or len(word) != len(target) or len(target) < 4:
            return False
        return word[0] == target[0] and word[-1] == target[-1] and sorted(word[1:-1]) == sorted(target[1:-1])

    def _contains_encoded_injection(self, value: str) -> bool:
        candidates = re.findall(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/=]{20,}(?![A-Za-z0-9+/=])", value)
        for candidate in candidates:
            try:
                decoded = base64.b64decode(candidate, validate=True).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if any(pattern.search(decoded) for pattern in self._patterns):
                return True
        return False


class OutputGuard:
    def __init__(self) -> None:
        self._patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (
                r"SYSTEM\s*:\s*You\s+are",
                r"API[_\s-]?KEY\s*[:=]\s*[A-Za-z0-9_\-]{12,}",
                r"<\s*img\b[^>]*\bsrc\s*=\s*['\"]?https?://",
                r"\b(ignore|disregard)\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
            )
        ]

    def inspect_text(self, value: str) -> GuardResult:
        if any(pattern.search(value) for pattern in self._patterns):
            return GuardResult(False, "unsafe model output detected")
        return GuardResult(True)

    def enforce_text(self, value: str) -> None:
        result = self.inspect_text(value)
        if not result.allowed:
            raise RequestPolicyError(result.reason or "response rejected by output guard")


def extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get("x-api-key")
    if header_key:
        return header_key

    authorization = request.headers.get("authorization")
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def verify_api_key(request: Request, allowed_keys: list[str]) -> None:
    if not allowed_keys:
        return

    provided = extract_api_key(request)
    if provided and any(secrets.compare_digest(provided, key) for key in allowed_keys):
        return

    raise AuthenticationError("valid API key required")
