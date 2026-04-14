---
name: output-schemas
description: JSON output schemas for all docsight commands — use this to parse --json results correctly
user-invocable: false
---

# Docsight Output Schemas

Reference this skill when parsing `--json` output from any docsight command.

## `docsight check --json`

```json
{
  "summary": {
    "total": 4,
    "healthy": 2,
    "stale": 1,
    "possibly_stale": 1,
    "unverified": 0
  },
  "docs": {
    "docs/auth-guide.md": {
      "status": "stale",
      "issues": [
        {
          "element_id": "src/auth.py::AuthManager.validate_token",
          "change_type": "signature",
          "confidence": 0.90,
          "hops": 0,
          "detail": "Signature of '...' has changed"
        }
      ]
    }
  },
  "stale_docs": [
    {
      "doc": "docs/auth-guide.md",
      "status": "stale",
      "issues": [...]
    }
  ]
}
```

**Key fields:**
- `change_type`: `"signature"` (API contract), `"body"` (behavior), `"transitive"` (dependency changed), `"reference_lost"` (element deleted/renamed)
- `confidence`: 0.0–1.0. >= 0.70 = STALE, < 0.70 = POSSIBLY_STALE
- `hops`: 0 = direct change, 1+ = transitive (through dependency chain)

## `docsight impact --json`

```json
{
  "target": "src/cache.py",
  "seed_elements": ["src/cache.py::cache_lookup", "src/cache.py::cache_store"],
  "affected_elements": [
    {"element_id": "src/auth.py::AuthManager.validate_token", "hops": 1}
  ],
  "affected_docs": [
    {"doc": "docs/auth-guide.md", "via": ["src/auth.py::AuthManager.validate_token"]}
  ]
}
```

**Key fields:**
- `seed_elements`: the elements directly targeted
- `affected_elements`: reverse-BFS dependents, sorted by hop distance
- `affected_docs.via`: which elements cause this doc to be affected

## `docsight diff --json`

```json
{
  "base": "main",
  "changed_elements": [
    {"element_id": "src/cache.py::cache_lookup", "change_type": "signature"},
    {"element_id": "src/auth.py::authenticate", "change_type": "deleted"}
  ],
  "affected_elements": [
    {"element_id": "src/auth.py::AuthManager.validate_token", "hops": 1}
  ],
  "affected_docs": [
    {
      "doc": "docs/auth-guide.md",
      "via": [
        {"element_id": "src/auth.py::AuthManager.validate_token", "hops": 1}
      ]
    }
  ]
}
```

**Key fields:**
- `change_type`: `"signature"`, `"body"`, or `"deleted"` (element removed/renamed)
- `base`: the comparison target (`"baseline"` or a git ref)

## `docsight coverage --json`

```json
{
  "mode": "api",
  "total": 39,
  "documented": 17,
  "undocumented": 22,
  "coverage_pct": 43.6,
  "undocumented_elements": ["src/config.py::load_config", ...]
}
```

## `docsight coverage --gaps --json`

```json
{
  "gap_files": [
    {"file": "src/config.py", "public_api": 3, "depended_on_by": 6}
  ],
  "total_gap_files": 1,
  "total_gap_elements": 3
}
```

**Key fields:**
- `depended_on_by`: number of other files that depend on this file (higher = more critical to document)
