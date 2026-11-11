"""Maskeert geheimen (API-sleutels, tokens, wachtwoorden) in weergaven, logs en MCP-uitvoer.

De oorspronkelijke tekst blijft in de database staan; alleen wat getoond of
doorgegeven wordt, wordt gemaskeerd.
"""
import re

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
# sleutel=waarde / sleutel: waarde met gevoelige naam
_KV = re.compile(
    r"(?i)\b((?:api[_-]?key|secret|token|passw(?:or)?d|wachtwoord|pwd|auth(?:orization)?|bearer|client[_-]?secret)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{6,})"
)
_URL_CRED = re.compile(r"(://[^/\s:@]+:)([^@\s/]{3,})(@)")
_BEARER = re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._\-]{12,})")

MASK = "•••[verborgen]•••"


def redact(text: str) -> str:
    if not text:
        return text
    for p in _PATTERNS:
        text = p.sub(MASK, text)
    text = _KV.sub(lambda m: m.group(1) + MASK, text)
    text = _URL_CRED.sub(lambda m: m.group(1) + MASK + m.group(3), text)
    text = _BEARER.sub(lambda m: m.group(1) + MASK, text)
    return text


def contains_secret(text: str) -> bool:
    return bool(text) and redact(text) != text
