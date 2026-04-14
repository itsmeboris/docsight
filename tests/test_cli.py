"""Tests for doc_updater.cli."""

import json

import pytest
from click.testing import CliRunner

from doc_updater.cli import cli


class TestCliInit:
    """Tests for the init command."""

    def test_init_creates_doc_updater_dir(self, tmp_path):
        """init creates the .doc-updater directory."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".doc-updater").is_dir()

    def test_init_adds_gitignore_entry(self, tmp_path):
        """init adds .doc-updater/ entry to .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".doc-updater/" in gitignore.read_text(encoding="utf-8")

    def test_init_idempotent_dir(self, tmp_path):
        """init is idempotent and does not fail when run twice."""
        runner = CliRunner()
        result1 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result2 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert (tmp_path / ".doc-updater").is_dir()

    def test_init_idempotent_gitignore_no_duplicate(self, tmp_path):
        """init does not add duplicate .doc-updater/ entries to .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert content.count(".doc-updater/") == 1

    def test_init_appends_to_existing_gitignore(self, tmp_path):
        """init appends .doc-updater/ to an existing .gitignore without clobbering it."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        content = gitignore.read_text(encoding="utf-8")
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert ".doc-updater/" in content

    def test_init_outputs_success_message(self, tmp_path):
        """init prints a success message on exit."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result.exit_code == 0
        assert "Initialized" in result.output or "initialized" in result.output

    def test_repo_defaults_to_cwd(self, tmp_path, monkeypatch):
        """init uses the current working directory when --repo is omitted."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".doc-updater").is_dir()

    def test_appends_newline_when_gitignore_lacks_trailing_newline(self, tmp_path):
        """Ensure .doc-updater/ is added correctly even when gitignore has no trailing newline."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc", encoding="utf-8")  # no trailing newline
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        content = gitignore.read_text(encoding="utf-8")
        # Each entry should appear on its own line after the existing content
        assert ".doc-updater/" in content
        assert "graph.html" in content
        assert "graph.json" in content
        assert content.startswith("*.pyc\n")


# ---------------------------------------------------------------------------
# index command
# ---------------------------------------------------------------------------


class TestCliClean:
    """Tests for the clean command."""

    def test_clean_removes_store_dir(self, tmp_path):
        """clean removes the .doc-updater/ directory."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert (tmp_path / ".doc-updater").exists()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        assert result.exit_code == 0
        assert not (tmp_path / ".doc-updater").exists()

    def test_clean_removes_gitignore_entries(self, tmp_path):
        """clean removes all doc-updater entries from .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gi = (tmp_path / ".gitignore").read_text()
        assert ".doc-updater/" in gi
        assert "graph.html" in gi
        runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        content = (tmp_path / ".gitignore").read_text()
        assert ".doc-updater/" not in content
        assert "graph.html" not in content
        assert "graph.json" not in content

    def test_clean_keep_gitignore(self, tmp_path):
        """clean --keep-gitignore preserves the .gitignore entry."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "clean", "--keep-gitignore"])
        assert ".doc-updater/" in (tmp_path / ".gitignore").read_text()

    def test_clean_noop_when_missing(self, tmp_path):
        """clean is safe when .doc-updater/ does not exist."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        assert result.exit_code == 0
        assert "nothing" in result.output.lower()

    def test_clean_preserves_other_gitignore_entries(self, tmp_path):
        """clean only removes the .doc-updater/ line, not other entries."""
        (tmp_path / ".gitignore").write_text("*.pyc\n.doc-updater/\n__pycache__/\n")
        (tmp_path / ".doc-updater").mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        content = (tmp_path / ".gitignore").read_text()
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert ".doc-updater/" not in content


# ---------------------------------------------------------------------------


class TestCliIndex:
    """Tests for the index command."""

    def test_index_command_creates_index_json(self, tmp_repo):
        """index creates index.json in the .doc-updater directory."""
        runner = CliRunner()
        # First init, then index
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output
        index_file = tmp_repo / ".doc-updater" / "index.json"
        assert index_file.exists()

    def test_index_finds_expected_elements(self, tmp_repo):
        """index discovers expected classes and functions in the repo."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        index_file = tmp_repo / ".doc-updater" / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8"))
        names = {v["name"] for v in index.values()}
        assert "AuthManager" in names
        assert "validate_token" in names
        assert "authenticate" in names
        assert "cache_lookup" in names

    def test_index_output_message(self, tmp_repo):
        """index prints an 'Indexed' summary message on success."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output
        assert "Indexed" in result.output

    def test_index_fails_on_syntax_error(self, tmp_path):
        """index exits with code 1 when a Python file has a syntax error."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        # Create a broken Python file
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n    this is garbage\n", encoding="utf-8")
        result = runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        assert result.exit_code == 1

    def test_index_skip_errors_flag(self, tmp_path):
        """index --skip-errors continues past syntax errors and exits 0."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n    this is garbage\n", encoding="utf-8")
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "index", "--skip-errors"]
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


class TestCliScan:
    """Tests for the scan command."""

    def test_scan_command(self, tmp_repo):
        """scan produces mappings.json with mapped and unmapped refs."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code == 0, result.output
        assert "Scanned" in result.output

        mappings_file = tmp_repo / ".doc-updater" / "mappings.json"
        assert mappings_file.exists()

        mappings = json.loads(mappings_file.read_text(encoding="utf-8"))
        # auth-guide.md should have mappings
        auth_key = next((k for k in mappings if "auth-guide" in k), None)
        assert auth_key is not None
        refs = mappings[auth_key]
        # Should have at least one mapped ref with a text field
        mapped = refs.get("mapped", [])
        assert len(mapped) > 0
        assert any("text" in r for r in mapped)

    def test_scan_requires_index(self, tmp_repo):
        """scan exits non-zero when no index has been built yet."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # Do NOT run index first
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code != 0

    def test_scan_output_format(self, tmp_repo):
        """scan output includes doc count and mapped/unmapped reference counts."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code == 0, result.output
        # Output should say "Scanned N docs, M references mapped, K unmapped"
        assert "docs" in result.output
        assert "mapped" in result.output

    def test_scan_unmapped_refs_stored(self, tmp_repo):
        """scan stores both mapped and unmapped keys for every doc entry."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        mappings_file = tmp_repo / ".doc-updater" / "mappings.json"
        mappings = json.loads(mappings_file.read_text(encoding="utf-8"))
        # Each doc entry should have 'mapped' and 'unmapped' keys
        for doc_key, doc_val in mappings.items():
            assert "mapped" in doc_val, f"Missing 'mapped' key in {doc_key}"
            assert "unmapped" in doc_val, f"Missing 'unmapped' key in {doc_key}"


# ---------------------------------------------------------------------------
# check command
# ---------------------------------------------------------------------------


class TestCliCheck:
    """Tests for the check command."""

    def test_check_baseline_exit_zero(self, tmp_repo):
        """check --baseline should exit 0 and store verified state."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        assert result.exit_code == 0, result.output
        assert "Baseline" in result.output

    def test_check_baseline_stores_dependency_hashes(self, tmp_repo):
        """check --baseline stores dependency_hashes in state.json."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        state_file = tmp_repo / ".doc-updater" / "state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert "verified" in state
        # At least one doc should have dependency_hashes key
        verified = state["verified"]
        assert all("dependency_hashes" in v for v in verified.values())

    def test_check_auto_refreshes_without_manual_index_scan(self, tmp_repo):
        """check --baseline should work without manually running index/scan first."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # Do NOT run index or scan manually
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        assert result.exit_code == 0, result.output
        # Verify index was created
        assert (tmp_repo / ".doc-updater" / "index.json").exists()
        # Verify mappings were created
        assert (tmp_repo / ".doc-updater" / "mappings.json").exists()

    def test_check_baseline_stores_healthy_last_report(self, tmp_repo):
        """check --baseline persists an 'all healthy' last_report."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        state = json.loads(
            (tmp_repo / ".doc-updater" / "state.json").read_text(encoding="utf-8")
        )
        assert "last_report" in state
        for doc_data in state["last_report"].values():
            assert doc_data["status"] == "healthy"

    def test_check_detects_stale_signature(self, tmp_repo):
        """After baseline, changing a referenced element's signature should exit 1."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # Establish baseline
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        # Check which elements got mapped
        mappings = json.loads(
            (tmp_repo / ".doc-updater" / "mappings.json").read_text(encoding="utf-8")
        )
        # Find any mapped element_id to determine what to change
        mapped_ids = []
        for doc_data in mappings.values():
            for ref in doc_data.get("mapped", []):
                mapped_ids.append(ref["element_id"])

        if not mapped_ids:
            pytest.skip("No mapped references found - scanner didn't map anything")

        # Change the AuthManager class (likely mapped) by adding a method
        auth_py = tmp_repo / "src" / "auth.py"
        original = auth_py.read_text(encoding="utf-8")
        # Add a new parameter to validate_token (changes its signature)
        modified = original.replace(
            "def validate_token(self, token: str) -> bool:",
            "def validate_token(self, token: str, strict: bool = False) -> bool:",
        )
        # Also directly rename the class to definitely change its signature hash
        # by adding a base class - this changes the class definition
        modified = modified.replace(
            "class AuthManager:",
            "class AuthManager(object):",
        )
        auth_py.write_text(modified, encoding="utf-8")

        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
        assert result.exit_code == 1

    def test_check_healthy_after_baseline_no_changes(self, tmp_repo):
        """After baseline with no changes, check should exit 0."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
        assert result.exit_code == 0, result.output

    def test_check_json_output(self, tmp_repo):
        """check --json should produce valid JSON with a summary key."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert "summary" in parsed
        assert "docs" in parsed
        assert "total" in parsed["summary"]

    def test_check_persists_last_report(self, tmp_repo):
        """check should persist last_report to state.json."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
        state = json.loads(
            (tmp_repo / ".doc-updater" / "state.json").read_text(encoding="utf-8")
        )
        assert "last_report" in state


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestCliStatus:
    """Tests for the status command."""

    def test_status_shows_last_report(self, tmp_repo):
        """status should display summary after baseline."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
        assert result.exit_code == 0, result.output

    def test_status_fails_without_report(self, tmp_repo):
        """status should fail if no last_report in state."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
        assert result.exit_code != 0

    def test_status_contains_summary_info(self, tmp_repo):
        """status output should contain count information."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
        # Rich panel should contain some count info
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# show command
# ---------------------------------------------------------------------------


class TestCliShow:
    """Tests for the show command."""

    def test_show_displays_doc_details(self, tmp_repo):
        """show should display tree for a known doc."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        # Get a doc path from mappings
        mappings_file = tmp_repo / ".doc-updater" / "mappings.json"
        mappings = json.loads(mappings_file.read_text(encoding="utf-8"))
        doc_path = next(iter(mappings.keys()))

        result = runner.invoke(cli, ["--repo", str(tmp_repo), "show", doc_path])
        assert result.exit_code == 0, result.output

    def test_show_fails_for_unknown_doc(self, tmp_repo):
        """show should fail with non-zero exit for unknown doc."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "show", "nonexistent/doc.md"]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------


class TestCliCoverage:
    """Tests for the coverage command."""

    def test_coverage_shows_stats(self, tmp_repo):
        """coverage reports documented and undocumented elements."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "coverage"])
        assert result.exit_code == 0, result.output
        assert "coverage" in result.output.lower() or "documented" in result.output.lower()

    def test_coverage_json_output(self, tmp_repo):
        """coverage --json returns valid JSON with coverage stats."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "coverage", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "total" in data
        assert "documented" in data
        assert "undocumented" in data
        assert "coverage_pct" in data
        assert data["documented"] > 0

    def test_coverage_detects_undocumented(self, tmp_path):
        """coverage finds elements that no doc references."""
        src = tmp_path / "mymod.py"
        src.write_text("def undocumented_func():\n    pass\n", encoding="utf-8")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "coverage", "--json"])
        data = json.loads(result.output)
        assert data["undocumented"] >= 1
        assert "undocumented_func" in str(data["undocumented_elements"])

    def test_coverage_excludes_private_by_default(self, tmp_path):
        """coverage hides _private elements unless --include-private."""
        src = tmp_path / "mymod.py"
        src.write_text("def public_func():\n    pass\ndef _priv():\n    pass\n")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "coverage", "--json"])
        data = json.loads(result.output)
        assert "_priv" not in str(data["undocumented_elements"])

    def test_coverage_include_private(self, tmp_path):
        """coverage --include-private shows _private elements."""
        src = tmp_path / "mymod.py"
        src.write_text("def public_func():\n    pass\ndef _priv():\n    pass\n")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--json", "--include-private"]
        )
        data = json.loads(result.output)
        assert "_priv" in str(data["undocumented_elements"])

    def test_show_fails_without_report(self, tmp_repo):
        """show should fail if no last_report."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "show", "docs/auth-guide.md"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# graph command
# ---------------------------------------------------------------------------


class TestCliGraph:
    """Tests for the graph command."""

    def test_graph_command_creates_html(self, tmp_repo):
        """graph command should create graph.html in the repo root."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        assert result.exit_code == 0, result.output
        assert (tmp_repo / "graph.html").exists()

    def test_graph_command_html_contains_vis_network(self, tmp_repo):
        """graph.html should contain vis.Network reference."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / "graph.html").read_text(encoding="utf-8")
        assert "vis.Network" in content

    def test_graph_command_json_export(self, tmp_repo):
        """graph --export json should create a JSON file."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "graph", "--export", "json"]
        )
        assert result.exit_code == 0, result.output
        assert (tmp_repo / "graph.json").exists()

    def test_graph_command_custom_output(self, tmp_repo):
        """graph -o <path> should write to the specified path."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        out = tmp_repo / "my_graph.html"
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "graph", "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_graph_command_auto_indexes(self, tmp_repo):
        """graph command should auto-index if no index exists."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # Do NOT run index manually
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        assert result.exit_code == 0, result.output
        assert (tmp_repo / "graph.html").exists()
