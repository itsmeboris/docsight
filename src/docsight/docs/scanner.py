"""Markdown document scanner that extracts raw code references."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawReference:
    """A raw code reference extracted from a markdown document."""

    text: str
    ref_type: str
    lineno: int
    confidence: float
    context: str = ""
    section: str = ""


# Regex patterns for prose backtick extraction (order matters: most specific first)
_RE_FILE_PATH = re.compile(r"`([^`]*?/[^`]*?)`")
_RE_METHOD_CALL = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\(\)`")
_RE_FUNC_CALL = re.compile(r"`([a-z_][A-Za-z0-9_]*)\(\)`")
_RE_CLASS_NAME = re.compile(r"`([A-Z][A-Za-z0-9_]*)`")

# Regex for class instantiation inside code blocks (fallback)
_RE_CLASS_INSTANTIATION = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\(\)")


def _extract_imports_from_code(code: str) -> list[str]:
    """AST-parse a code block and return imported names."""
    names: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.append(alias.asname if alias.asname else alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.asname if alias.asname else alias.name)
    return names


def _extract_refs_from_code_block(
    block_lines: list[str],
    start_lineno: int,
    section: str,
) -> list[RawReference]:
    """Extract references from a fenced code block."""
    refs: list[RawReference] = []
    code = "\n".join(block_lines)

    seen: set[str] = set()

    # Try AST import extraction first
    for name in _extract_imports_from_code(code):
        if name not in seen:
            seen.add(name)
            refs.append(
                RawReference(
                    text=name,
                    ref_type="import_code_block",
                    lineno=start_lineno,
                    confidence=0.80,
                    section=section,
                )
            )

    # Regex fallback: ClassName() patterns
    for m in _RE_CLASS_INSTANTIATION.finditer(code):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            refs.append(
                RawReference(
                    text=name,
                    ref_type="class_instantiation_code_block",
                    lineno=start_lineno,
                    confidence=0.70,
                    section=section,
                )
            )

    return refs


def _extract_refs_from_prose_line(
    line: str,
    lineno: int,
    section: str,
) -> list[RawReference]:
    """Extract references from a prose line (not inside a code block)."""
    refs: list[RawReference] = []
    seen: set[str] = set()

    # File paths first (highest confidence, must contain /)
    for m in _RE_FILE_PATH.finditer(line):
        text = m.group(1)
        if text not in seen:
            seen.add(text)
            refs.append(
                RawReference(
                    text=text,
                    ref_type="file_path_backtick",
                    lineno=lineno,
                    confidence=0.95,
                    context=line.strip(),
                    section=section,
                )
            )

    # Dotted method calls: `Class.method()`
    for m in _RE_METHOD_CALL.finditer(line):
        text = m.group(1)
        if text not in seen:
            seen.add(text)
            refs.append(
                RawReference(
                    text=text,
                    ref_type="method_call_backtick",
                    lineno=lineno,
                    confidence=0.90,
                    context=line.strip(),
                    section=section,
                )
            )

    # Function calls: `lowercase_func()`
    for m in _RE_FUNC_CALL.finditer(line):
        text = m.group(1)
        if text not in seen:
            seen.add(text)
            refs.append(
                RawReference(
                    text=text,
                    ref_type="function_call_backtick",
                    lineno=lineno,
                    confidence=0.90,
                    context=line.strip(),
                    section=section,
                )
            )

    # Class names: `UpperCamelCase`
    for m in _RE_CLASS_NAME.finditer(line):
        text = m.group(1)
        if text not in seen:
            seen.add(text)
            refs.append(
                RawReference(
                    text=text,
                    ref_type="class_name_backtick",
                    lineno=lineno,
                    confidence=0.85,
                    context=line.strip(),
                    section=section,
                )
            )

    return refs


_RE_HEADING = re.compile(r"^#{1,6}\s+(.*)")
_RE_CODE_FENCE = re.compile(r"^```")


class DocScanner:
    """Scan markdown text and extract raw code references."""

    def scan_text(self, text: str) -> list[RawReference]:
        """Scan markdown text and return all extracted RawReferences."""
        lines = text.splitlines()
        refs: list[RawReference] = []

        current_section = ""
        in_code_block = False
        code_block_lines: list[str] = []
        code_block_start = 0

        for lineno, line in enumerate(lines, start=1):
            if _RE_CODE_FENCE.match(line):
                if not in_code_block:
                    # Entering code block
                    in_code_block = True
                    code_block_lines = []
                    code_block_start = lineno
                else:
                    # Leaving code block — process accumulated lines
                    block_refs = _extract_refs_from_code_block(
                        code_block_lines, code_block_start, current_section
                    )
                    refs.extend(block_refs)
                    in_code_block = False
                    code_block_lines = []
                continue

            if in_code_block:
                code_block_lines.append(line)
                continue

            # Check for heading
            heading_m = _RE_HEADING.match(line)
            if heading_m:
                current_section = heading_m.group(1).strip()
                continue

            # Prose line
            line_refs = _extract_refs_from_prose_line(line, lineno, current_section)
            refs.extend(line_refs)

        return refs

    def scan_file(self, path: Path) -> list[RawReference]:
        """Scan a markdown file and return all extracted RawReferences."""
        text = Path(path).read_text(encoding="utf-8")
        return self.scan_text(text)
