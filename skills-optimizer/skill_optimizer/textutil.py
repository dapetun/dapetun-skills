"""Deterministic text utilities for static/heuristic analysis."""

from __future__ import annotations

import hashlib
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,}", re.IGNORECASE)
_CAPABILITY_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]|\d+\.)\s+(.+)$|^(?:you (?:can|should|must)|this skill)\b.+$"
)
_TRIGGER_HINTS = (
    "use when",
    "use if",
    "when the user",
    "when working",
    "trigger",
    "applies when",
    "relevant when",
)
_EXCLUSION_HINTS = (
    "do not",
    "don't",
    "never",
    "not for",
    "avoid when",
    "out of scope",
    "does not",
)
_STOP = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "when",
    "that",
    "this",
    "these",
    "those",
    "from",
    "into",
    "as",
    "by",
    "is",
    "are",
    "be",
    "been",
    "being",
    "it",
    "its",
    "you",
    "your",
    "use",
    "used",
    "using",
    "skill",
    "skills",
    "do",
    "not",
    "dont",
    "never",
    "avoid",
    "must",
    "always",
    "should",
    "can",
    "will",
    "may",
    "if",
    "else",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def content_tokens(text: str) -> set[str]:
    """Токены без стоп-слов (для сравнения смыслов, не синтаксиса)."""
    return {t for t in tokenize(text) if t not in _STOP and len(t) > 2}


def token_set(text: str) -> set[str]:
    return set(tokenize(text))


def jaccard(a: set[str], b: set[str]) -> float:
    # Пустые множества не считать «полным совпадением» - иначе YAML-fail → ложный OVERLAP.
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def estimate_tokens(text: str) -> int:
    # Rough deterministic estimate (~4 chars/token) for context-cost reporting.
    return max(1, (len(text or "") + 3) // 4) if text else 0


def extract_markdown_links(body: str) -> list[str]:
    links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", body or "")
    bare = re.findall(
        r"(?m)^\s*(?:See|Read|Open|Run|Use)\s+`?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)`?",
        body or "",
    )
    scripts = re.findall(r"(?m)\b((?:scripts|references|assets)/[A-Za-z0-9_./\\-]+)", body or "")
    result: list[str] = []
    for item in links + bare + scripts:
        item = item.strip().strip("`'\"")
        if item.startswith(("http://", "https://", "mailto:")):
            continue
        if item:
            result.append(item.replace("\\", "/"))
    # Preserve order, drop duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for path in result:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def extract_capabilities(description: str, body: str) -> list[str]:
    caps: list[str] = []
    for source in (description, body):
        for line in (source or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower.startswith(("#", "```")):
                continue
            if any(
                key in lower
                for key in (
                    "this skill",
                    "you will",
                    "you should",
                    "steps",
                    "capabilities",
                    "purpose",
                )
            ) or stripped.startswith(("-", "*", "1.", "2.", "3.")):
                clean = re.sub(r"^[-*]\s+", "", stripped)
                clean = re.sub(r"^\d+\.\s+", "", clean)
                if 8 <= len(clean) <= 160:
                    caps.append(normalize_ws(clean))
    # Also pull verb phrases from description sentences
    for part in re.split(r"[.;]", description or ""):
        part = normalize_ws(part)
        if 8 <= len(part) <= 160:
            caps.append(part)
    return _dedupe_keep_order(caps)[:40]


def extract_triggers(description: str, body: str) -> list[str]:
    triggers: list[str] = []
    text = f"{description}\n{body}"
    for line in text.splitlines():
        lower = line.lower()
        if any(h in lower for h in _TRIGGER_HINTS):
            triggers.append(normalize_ws(line))
    # Phrases after "use when" / "use if" only (not every description token)
    desc = description or ""
    for m in re.finditer(r"(?i)\buse when (.+?)(?:\.|$)", desc):
        for chunk in re.split(r"[,;/]| and | or ", m.group(1)):
            chunk = normalize_ws(chunk)
            if chunk:
                triggers.append(chunk)
    for m in re.finditer(r"(?i)\buse if (.+?)(?:\.|$)", desc):
        for chunk in re.split(r"[,;/]| and | or ", m.group(1)):
            chunk = normalize_ws(chunk)
            if chunk:
                triggers.append(chunk)
    return _dedupe_keep_order(triggers)[:50]


def extract_exclusions(description: str, body: str) -> list[str]:
    """Только явные exclusion-фрагменты, не вся description с «Do not use for…» в хвосте."""
    exclusions: list[str] = []
    for line in f"{description}\n{body}".splitlines():
        lower = line.lower().strip()
        if not lower:
            continue
        for hint in _EXCLUSION_HINTS:
            pos = lower.find(hint)
            if pos < 0:
                continue
            # Подсказка в начале строки / пункта, либо после разделителя предложения
            prefix = lower[:pos]
            near_start = pos <= 48
            after_break = (not prefix) or prefix.endswith(
                (". ", "; ", ": ", "- ", "* ", ") ", "] ")
            )
            if not (near_start or after_break):
                continue
            clause = lower[pos:]
            # Обрезать длинные хвосты description
            if len(clause) > 220:
                clause = clause[:220]
            exclusions.append(normalize_ws(clause))
            break
    return _dedupe_keep_order(exclusions)[:40]


def repeated_instruction_lines(body: str, min_count: int = 3) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for line in (body or "").splitlines():
        norm = normalize_ws(line)
        if len(norm) < 20:
            continue
        counter[norm] += 1
    return [(line, count) for line, count in counter.most_common() if count >= min_count]


def contradiction_pairs(a_excl: list[str], b_caps: list[str]) -> list[tuple[str, str]]:
    """Heuristic: exclusion in A contradicts capability/trigger language in B."""
    pairs: list[tuple[str, str]] = []
    for excl in a_excl:
        excl_tokens = content_tokens(excl)
        if len(excl_tokens) < 3:
            continue
        for cap in b_caps:
            cap_tokens = content_tokens(cap)
            if len(cap_tokens) < 3:
                continue
            # Нужен содержательный overlap, не 2 случайных слова
            if len(excl_tokens & cap_tokens) >= 4:
                pairs.append((excl, cap))
    return pairs[:20]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
