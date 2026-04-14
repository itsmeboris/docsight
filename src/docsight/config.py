"""Load docsight configuration from pyproject.toml."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


def load_config(repo: Path) -> dict:
    """Read ``[tool.docsight]`` from *repo*/pyproject.toml.

    Returns an empty dict when the file or section is absent or when
    any intermediate value has the wrong type (e.g. ``tool = "string"``
    instead of a table).
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-except
        return {}
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}
    section = tool.get("docsight")
    if not isinstance(section, dict):
        return {}
    return section


# Directories that are always excluded (contain repo copies or generated code)
_BUILTIN_EXCLUDES = [
    ".claude/worktrees/",
    ".worktrees/",
    "node_modules/",
    ".git/",
    "__pycache__/",
]


def get_exclude_patterns(config: dict) -> list[str]:
    """Return the ``exclude`` list from config, merged with built-in excludes.

    Built-in excludes (``.claude/worktrees/``, ``node_modules/``, etc.)
    are always applied.  Silently drops non-string entries so a mistyped
    value never crashes the CLI.
    """
    raw = config.get("exclude", [])
    if isinstance(raw, str):
        raw = [raw]
    elif not isinstance(raw, list):
        raw = []
    user = [item for item in raw if isinstance(item, str)]
    # Merge: built-in + user, deduplicated
    seen: set[str] = set()
    result: list[str] = []
    for pat in _BUILTIN_EXCLUDES + user:
        if pat not in seen:
            seen.add(pat)
            result.append(pat)
    return result


def should_exclude(rel_path: str, patterns: list[str]) -> bool:
    """Return *True* when *rel_path* matches any exclude pattern.

    Matching rules (all checked against the POSIX-style relative path):
    - Exact prefix:  ``".claude/"`` matches ``".claude/foo.py"``
    - Glob/fnmatch:  ``"tests/**"`` matches ``"tests/test_foo.py"``
    - Plain fnmatch:  ``"*.generated.py"`` matches ``"src/schema.generated.py"``
    """
    posix = rel_path.replace("\\", "/")
    for pat in patterns:
        pat_posix = pat.replace("\\", "/")
        # Prefix match (directory pattern like ".claude/" or "tests/")
        if pat_posix.endswith("/") and posix.startswith(pat_posix):
            return True
        # Also check without trailing slash for directory patterns
        if not pat_posix.endswith("/") and "/" not in pat_posix:
            # Simple name — treat as prefix if it looks like a directory
            if posix.startswith(pat_posix + "/"):
                return True
        # fnmatch on the full relative path
        if fnmatch(posix, pat_posix):
            return True
        # fnmatch on just the filename component
        if "/" not in pat_posix and fnmatch(posix.split("/")[-1], pat_posix):
            return True
    return False
