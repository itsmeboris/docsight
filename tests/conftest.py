"""Shared pytest fixtures for doc-updater tests."""

import pytest


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repository with sample Python source and docs."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # src/auth.py
    (src_dir / "auth.py").write_text(
        """\
from src.cache import cache_lookup


class AuthManager:
    \"\"\"Manages authentication for the application.\"\"\"

    def validate_token(self, token: str) -> bool:
        \"\"\"Validate an authentication token.\"\"\"
        cached = cache_lookup(token)
        if cached:
            return True
        return self._decode(token)

    def _decode(self, token: str) -> bool:
        \"\"\"Decode and verify a token.\"\"\"
        return bool(token)


def authenticate(username: str, password: str) -> bool:
    \"\"\"Authenticate a user with username and password.\"\"\"
    mgr = AuthManager()
    return mgr.validate_token(f"{username}:{password}")
""",
        encoding="utf-8",
    )

    # src/cache.py
    (src_dir / "cache.py").write_text(
        """\
def cache_lookup(key: str) -> str:
    \"\"\"Look up a value in the cache by key.\"\"\"
    return ""


def cache_store(key: str, value: str) -> None:
    \"\"\"Store a value in the cache.\"\"\"
""",
        encoding="utf-8",
    )

    # docs/auth-guide.md
    (docs_dir / "auth-guide.md").write_text(
        """\
# Authentication Guide

This guide covers the AuthManager class and the authenticate() function
defined in src/auth.py.

## Usage

Use validate_token() to check whether a token is valid:

```python
mgr = AuthManager()
result = mgr.validate_token("my-token")
```

You can also call authenticate() directly.
""",
        encoding="utf-8",
    )

    # docs/cache-guide.md
    (docs_dir / "cache-guide.md").write_text(
        """\
# Cache Guide

This guide covers cache_lookup() and cache_store() from src/cache.py.

## Lookup

Call cache_lookup() to retrieve a cached value by key.

## Storage

Call cache_store() to persist a key/value pair.
""",
        encoding="utf-8",
    )

    return tmp_path
