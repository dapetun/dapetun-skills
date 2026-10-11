"""Minimal YAML subset loader (stdlib only) for frontmatter and config."""

from __future__ import annotations

from typing import Any


class SimpleYAMLError(ValueError):
    """Raised when the subset parser cannot read a document."""


def loads(text: str) -> Any:
    """Parse a restricted YAML document into Python objects."""
    lines = _preprocess(text)
    if not lines:
        return None
    value, _ = _parse_block(lines, 0, 0)
    return value


def load(path_text: str) -> Any:
    return loads(path_text)


def _preprocess(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        # Full-line comments
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        # Strip inline comments when not inside quotes
        line = _strip_inline_comment(raw.strip())
        if line:
            result.append((indent, line))
    return result


def _strip_inline_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1].isspace():
                return line[:i].rstrip()
    return line


def _parse_block(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[Any, int]:
    if idx >= len(lines):
        return None, idx
    cur_indent, content = lines[idx]
    if cur_indent < indent:
        return None, idx
    if content.startswith("- "):
        return _parse_list(lines, idx, cur_indent)
    if ":" in content:
        return _parse_mapping(lines, idx, cur_indent)
    return _parse_scalar(content), idx + 1


def _parse_mapping(
    lines: list[tuple[int, str]], idx: int, indent: int
) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise SimpleYAMLError(f"Unexpected indent at: {content}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise SimpleYAMLError(f"Expected key: value at: {content}")
        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "" or rest == "|":
            # Nested value or empty
            if idx + 1 < len(lines) and lines[idx + 1][0] > indent:
                child_indent = lines[idx + 1][0]
                value, idx = _parse_block(lines, idx + 1, child_indent)
            else:
                value = None
                idx += 1
        else:
            value = _parse_scalar(rest)
            idx += 1
            # Inline key followed by nested indented block is not supported after scalar
        mapping[key] = value
    return mapping, idx


def _parse_list(
    lines: list[tuple[int, str]], idx: int, indent: int
) -> tuple[list[Any], int]:
    items: list[Any] = []
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise SimpleYAMLError(f"Unexpected indent in list at: {content}")
        if not content.startswith("- "):
            break
        rest = content[2:].strip()
        if rest == "" or rest == "|":
            if idx + 1 < len(lines) and lines[idx + 1][0] > indent:
                child_indent = lines[idx + 1][0]
                value, idx = _parse_block(lines, idx + 1, child_indent)
            else:
                value = None
                idx += 1
        elif ":" in rest and not rest.startswith(("'", '"')):
            # List of inline mappings: - key: value
            # Collect continuation lines at greater indent as part of mapping
            key, _, val = rest.partition(":")
            mapping: dict[str, Any] = {key.strip(): _parse_scalar(val.strip())}
            idx += 1
            while idx < len(lines) and lines[idx][0] > indent:
                nested_indent, nested = lines[idx]
                if nested.startswith("- "):
                    break
                if ":" in nested:
                    nk, _, nv = nested.partition(":")
                    nv = nv.strip()
                    if nv == "":
                        if idx + 1 < len(lines) and lines[idx + 1][0] > nested_indent:
                            child, idx = _parse_block(lines, idx + 1, lines[idx + 1][0])
                            mapping[nk.strip()] = child
                        else:
                            mapping[nk.strip()] = None
                            idx += 1
                    else:
                        mapping[nk.strip()] = _parse_scalar(nv)
                        idx += 1
                else:
                    break
            value = mapping
        else:
            value = _parse_scalar(rest)
            idx += 1
        items.append(value)
    return items, idx


def _parse_scalar(text: str) -> Any:
    if text == "" or text in {"null", "Null", "NULL", "~"}:
        return None
    if text in {"true", "True", "TRUE"}:
        return True
    if text in {"false", "False", "FALSE"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        inner = text[1:-1]
        # Reject obviously unclosed / broken quoted forms already handled by ends-with
        return inner
    # Reject broken flow collections (common frontmatter mistake)
    if text.startswith("[") or text.startswith("{"):
        if text.startswith("[") and not text.endswith("]"):
            raise SimpleYAMLError(f"Unclosed flow sequence: {text}")
        if text.startswith("{") and not text.endswith("}"):
            raise SimpleYAMLError(f"Unclosed flow mapping: {text}")
        # Minimal support: empty or simple comma lists
        if text == "[]":
            return []
        if text == "{}":
            return {}
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (text.startswith('"') and not text.endswith('"')) or (
        text.startswith("'") and not text.endswith("'")
    ):
        raise SimpleYAMLError(f"Unclosed quoted string: {text}")
    # integers / floats
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    if any(c in text for c in ".eE") and _is_float(text):
        return float(text)
    return text


def _is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False
