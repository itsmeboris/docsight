"""Tests for docsight.config — exclude patterns and config loading."""

from docsight.config import get_exclude_patterns, load_config, should_exclude


class TestLoadConfig:
    """Tests for loading config from pyproject.toml."""

    def test_returns_empty_dict_when_no_pyproject(self, tmp_path):
        """Returns {} when pyproject.toml does not exist."""
        assert load_config(tmp_path) == {}

    def test_returns_empty_dict_when_no_tool_section(self, tmp_path):
        """Returns {} when pyproject.toml has no [tool.docsight]."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "foo"\n', encoding="utf-8"
        )
        assert load_config(tmp_path) == {}

    def test_returns_config_dict(self, tmp_path):
        """Returns the [tool.docsight] section."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.docsight]\nexclude = [".claude/", "tests/"]\n',
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg["exclude"] == [".claude/", "tests/"]

    def test_handles_malformed_toml(self, tmp_path):
        """Returns {} on malformed TOML."""
        (tmp_path / "pyproject.toml").write_text("[[invalid", encoding="utf-8")
        assert load_config(tmp_path) == {}

    def test_handles_tool_as_non_table(self, tmp_path):
        """Returns {} when [tool] is not a table (e.g. tool = 'string')."""
        (tmp_path / "pyproject.toml").write_text(
            'tool = "not a table"\n', encoding="utf-8"
        )
        assert load_config(tmp_path) == {}

    def test_handles_docsight_as_non_table(self, tmp_path):
        """Returns {} when docsight value is not a table."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool]\ndocsight = "not a table"\n', encoding="utf-8"
        )
        assert load_config(tmp_path) == {}

    def test_handles_docsight_as_integer(self, tmp_path):
        """Returns {} when docsight value is an integer."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool]\ndocsight = 42\n', encoding="utf-8"
        )
        assert load_config(tmp_path) == {}


class TestGetExcludePatterns:
    """Tests for get_exclude_patterns."""

    def test_always_includes_builtin_excludes(self):
        """Built-in excludes are always present even with no user config."""
        result = get_exclude_patterns({})
        assert ".claude/worktrees/" in result
        assert "node_modules/" in result
        assert "__pycache__/" in result

    def test_merges_user_config_with_builtins(self):
        """User exclude patterns are appended after built-ins."""
        result = get_exclude_patterns({"exclude": ["vendor/", "generated/"]})
        assert "vendor/" in result
        assert "generated/" in result
        assert ".claude/worktrees/" in result  # built-in still present

    def test_deduplicates(self):
        """User patterns that overlap built-ins are not duplicated."""
        result = get_exclude_patterns({"exclude": ["node_modules/", "extra/"]})
        assert result.count("node_modules/") == 1

    def test_wraps_string_in_list(self):
        """Wraps a single string value into a list."""
        result = get_exclude_patterns({"exclude": "tests/"})
        assert "tests/" in result

    def test_ignores_non_list_non_string_value(self):
        """Returns only built-ins when exclude is an int, bool, or dict."""
        for bad in (42, True, {"bad": "value"}):
            result = get_exclude_patterns({"exclude": bad})
            assert ".claude/worktrees/" in result
            assert "vendor/" not in result  # no user patterns leaked in

    def test_drops_non_string_items_from_list(self):
        """Silently drops non-string entries from a list."""
        result = get_exclude_patterns({"exclude": ["tests/", 42, None, "vendor/"]})
        assert "tests/" in result
        assert "vendor/" in result


class TestShouldExclude:
    """Tests for should_exclude path matching."""

    def test_directory_prefix_match(self):
        """Patterns ending with / match as directory prefixes."""
        assert should_exclude(".claude/foo.py", [".claude/"])
        assert should_exclude("tests/test_foo.py", ["tests/"])

    def test_no_match(self):
        """Returns False when no pattern matches."""
        assert not should_exclude("src/main.py", [".claude/", "tests/"])

    def test_glob_pattern(self):
        """Glob patterns like *.generated.py match filenames."""
        assert should_exclude("src/schema.generated.py", ["*.generated.py"])

    def test_fnmatch_full_path(self):
        """fnmatch works on the full relative path."""
        assert should_exclude("vendor/lib/util.py", ["vendor/*"])

    def test_nested_directory_prefix(self):
        """Nested directory prefix matching."""
        assert should_exclude(".claude/skills/foo.md", [".claude/"])
        assert not should_exclude("src/.claude_compat.py", [".claude/"])

    def test_directory_without_trailing_slash(self):
        """Directory name without trailing slash matches as prefix."""
        assert should_exclude("worktrees/branch/file.py", ["worktrees"])

    def test_multiple_patterns(self):
        """Returns True if any pattern matches."""
        patterns = [".claude/", "tests/", "*.bak"]
        assert should_exclude("tests/test_x.py", patterns)
        assert should_exclude("data.bak", patterns)
        assert not should_exclude("src/main.py", patterns)

    def test_empty_patterns(self):
        """Returns False when patterns list is empty."""
        assert not should_exclude("anything.py", [])
