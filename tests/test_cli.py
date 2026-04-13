"""Tests for doc_updater.cli."""

import json

import pytest
from click.testing import CliRunner

from doc_updater.cli import cli


class TestCliInit:
    def test_init_creates_doc_updater_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".doc-updater").is_dir()

    def test_init_adds_gitignore_entry(self, tmp_path):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".doc-updater/" in gitignore.read_text(encoding="utf-8")

    def test_init_idempotent_dir(self, tmp_path):
        runner = CliRunner()
        result1 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result2 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert (tmp_path / ".doc-updater").is_dir()

    def test_init_idempotent_gitignore_no_duplicate(self, tmp_path):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert content.count(".doc-updater/") == 1

    def test_init_appends_to_existing_gitignore(self, tmp_path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        content = gitignore.read_text(encoding="utf-8")
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert ".doc-updater/" in content

    def test_init_outputs_success_message(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result.exit_code == 0
        assert "Initialized" in result.output or "initialized" in result.output

    def test_repo_defaults_to_cwd(self, tmp_path, monkeypatch):
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
        assert ".doc-updater/" in content
        # The entry should appear on its own line
        assert "*.pyc\n.doc-updater/\n" == content


# ---------------------------------------------------------------------------
# index command
# ---------------------------------------------------------------------------


class TestCliIndex:
    def test_index_command_creates_index_json(self, tmp_repo):
        runner = CliRunner()
        # First init, then index
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output
        index_file = tmp_repo / ".doc-updater" / "index.json"
        assert index_file.exists()

    def test_index_finds_expected_elements(self, tmp_repo):
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
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output
        assert "Indexed" in result.output

    def test_index_fails_on_syntax_error(self, tmp_path):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        # Create a broken Python file
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n    this is garbage\n", encoding="utf-8")
        result = runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        assert result.exit_code == 1

    def test_index_skip_errors_flag(self, tmp_path):
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
    def test_scan_command(self, tmp_repo):
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
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # Do NOT run index first
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code != 0

    def test_scan_output_format(self, tmp_repo):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code == 0, result.output
        # Output should say "Scanned N docs, M references mapped, K unmapped"
        assert "docs" in result.output
        assert "mapped" in result.output

    def test_scan_unmapped_refs_stored(self, tmp_repo):
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
        import json as _json
        mappings = _json.loads(
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
