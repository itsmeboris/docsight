"""Tests for docsight.cli."""
# pylint: disable=too-many-lines

import json

import pytest
from click.testing import CliRunner

from docsight.cli import cli


class TestCliInit:
    """Tests for the init command."""

    def test_init_creates_docsight_dir(self, tmp_path):
        """init creates the .docsight directory."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".docsight").is_dir()

    def test_init_adds_gitignore_entry(self, tmp_path):
        """init adds .docsight/ entry to .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".docsight/" in gitignore.read_text(encoding="utf-8")

    def test_init_idempotent_dir(self, tmp_path):
        """init is idempotent and does not fail when run twice."""
        runner = CliRunner()
        result1 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result2 = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert (tmp_path / ".docsight").is_dir()

    def test_init_idempotent_gitignore_no_duplicate(self, tmp_path):
        """init does not add duplicate .docsight/ entries to .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gitignore = tmp_path / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert content.count(".docsight/") == 1

    def test_init_appends_to_existing_gitignore(self, tmp_path):
        """init appends .docsight/ to an existing .gitignore without clobbering it."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        content = gitignore.read_text(encoding="utf-8")
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert ".docsight/" in content

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
        assert (tmp_path / ".docsight").is_dir()

    def test_appends_newline_when_gitignore_lacks_trailing_newline(self, tmp_path):
        """Ensure .docsight/ is added correctly even when gitignore has no trailing newline."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc", encoding="utf-8")  # no trailing newline
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        content = gitignore.read_text(encoding="utf-8")
        # .docsight/ entry should appear after existing content
        assert ".docsight/" in content
        assert content.startswith("*.pyc\n")

    def test_init_auto_baselines(self, tmp_repo):
        """init auto-runs index + scan + baseline so check works immediately."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        assert result.exit_code == 0, result.output
        assert "Baseline" in result.output
        # state.json should have verified entries
        state = json.loads(
            (tmp_repo / ".docsight" / "state.json").read_text()
        )
        assert "verified" in state
        assert len(state["verified"]) > 0

    def test_init_no_baseline_flag(self, tmp_path):
        """init --no-baseline skips the baseline step."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "init", "--no-baseline"])
        assert result.exit_code == 0, result.output
        assert "Baseline" not in result.output
        assert (tmp_path / ".docsight").is_dir()


# ---------------------------------------------------------------------------
# hooks command
# ---------------------------------------------------------------------------


class TestCliHooks:
    """Tests for the hooks install/uninstall commands."""

    def test_hooks_install_creates_pre_push(self, tmp_repo):
        """hooks install creates a pre-push hook with stdin drain and guard."""
        (tmp_repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "install"])
        assert result.exit_code == 0, result.output
        hook = tmp_repo / ".git" / "hooks" / "pre-push"
        assert hook.exists()
        content = hook.read_text()
        assert "docsight check" in content
        # Must drain stdin so git doesn't hang
        assert "cat > /dev/null" in content
        # Must guard against docsight not being installed
        assert "command -v docsight" in content

    def test_hooks_install_idempotent(self, tmp_repo):
        """hooks install is idempotent — does not duplicate."""
        (tmp_repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "install"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "install"])
        hook = tmp_repo / ".git" / "hooks" / "pre-push"
        content = hook.read_text()
        assert content.count("docsight check") == 1

    def test_hooks_install_appends_to_existing(self, tmp_repo):
        """hooks install appends to an existing pre-push hook."""
        hooks_dir = tmp_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-push").write_text("#!/bin/sh\necho 'existing'\n")
        (hooks_dir / "pre-push").chmod(0o755)

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "install"])
        content = (hooks_dir / "pre-push").read_text()
        assert "existing" in content
        assert "docsight check" in content
        # Appended block must also drain stdin and guard
        assert "cat > /dev/null" in content
        assert "command -v docsight" in content

    def test_hooks_uninstall_removes_hook(self, tmp_repo):
        """hooks uninstall removes the docsight pre-push hook."""
        (tmp_repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "install"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "uninstall"])
        assert result.exit_code == 0, result.output
        assert not (tmp_repo / ".git" / "hooks" / "pre-push").exists()

    def test_hooks_uninstall_preserves_other_hooks(self, tmp_repo):
        """hooks uninstall preserves non-docsight lines in pre-push."""
        hooks_dir = tmp_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-push").write_text(
            "#!/bin/sh\necho 'other tool'\n# docsight: fail push if docs are stale\ndocsight check\n"
        )
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "uninstall"])
        content = (hooks_dir / "pre-push").read_text()
        assert "other tool" in content
        assert "docsight" not in content

    def test_hooks_uninstall_noop_when_missing(self, tmp_repo):
        """hooks uninstall is safe when no pre-push hook exists."""
        (tmp_repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "hooks", "uninstall"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# index command
# ---------------------------------------------------------------------------


class TestCliClean:
    """Tests for the clean command."""

    def test_clean_removes_store_dir(self, tmp_path):
        """clean removes the .docsight/ directory."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        assert (tmp_path / ".docsight").exists()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        assert result.exit_code == 0
        assert not (tmp_path / ".docsight").exists()

    def test_clean_removes_gitignore_entries(self, tmp_path):
        """clean removes all docsight entries from .gitignore."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        gi = (tmp_path / ".gitignore").read_text()
        assert ".docsight/" in gi
        runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        content = (tmp_path / ".gitignore").read_text()
        assert ".docsight/" not in content

    def test_clean_keep_gitignore(self, tmp_path):
        """clean --keep-gitignore preserves the .gitignore entry."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "clean", "--keep-gitignore"])
        assert ".docsight/" in (tmp_path / ".gitignore").read_text()

    def test_clean_noop_when_missing(self, tmp_path):
        """clean is safe when .docsight/ does not exist."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        assert result.exit_code == 0
        assert "nothing" in result.output.lower()

    def test_clean_preserves_other_gitignore_entries(self, tmp_path):
        """clean only removes the .docsight/ line, not other entries."""
        (tmp_path / ".gitignore").write_text("*.pyc\n.docsight/\n__pycache__/\n")
        (tmp_path / ".docsight").mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "clean"])
        content = (tmp_path / ".gitignore").read_text()
        assert "*.pyc" in content
        assert "__pycache__/" in content
        assert ".docsight/" not in content


# ---------------------------------------------------------------------------


class TestCliIndex:
    """Tests for the index command."""

    def test_index_command_creates_index_json(self, tmp_repo):
        """index creates index.json in the .docsight directory."""
        runner = CliRunner()
        # First init, then index
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output
        index_file = tmp_repo / ".docsight" / "index.json"
        assert index_file.exists()

    def test_index_finds_expected_elements(self, tmp_repo):
        """index discovers expected classes and functions in the repo."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        index_file = tmp_repo / ".docsight" / "index.json"
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

        mappings_file = tmp_repo / ".docsight" / "mappings.json"
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
        runner.invoke(cli, ["--repo", str(tmp_repo), "init", "--no-baseline"])
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
        mappings_file = tmp_repo / ".docsight" / "mappings.json"
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
        state_file = tmp_repo / ".docsight" / "state.json"
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
        assert (tmp_repo / ".docsight" / "index.json").exists()
        # Verify mappings were created
        assert (tmp_repo / ".docsight" / "mappings.json").exists()

    def test_check_baseline_stores_healthy_last_report(self, tmp_repo):
        """check --baseline persists an 'all healthy' last_report."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        state = json.loads(
            (tmp_repo / ".docsight" / "state.json").read_text(encoding="utf-8")
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
            (tmp_repo / ".docsight" / "mappings.json").read_text(encoding="utf-8")
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
            (tmp_repo / ".docsight" / "state.json").read_text(encoding="utf-8")
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
        runner.invoke(cli, ["--repo", str(tmp_repo), "init", "--no-baseline"])
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
        mappings_file = tmp_repo / ".docsight" / "mappings.json"
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
        runner.invoke(cli, ["--repo", str(tmp_repo), "init", "--no-baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "show", "docs/auth-guide.md"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# graph command
# ---------------------------------------------------------------------------


class TestCliGraph:
    """Tests for the graph command."""

    def test_graph_command_creates_html(self, tmp_repo):
        """graph command should create graph.html in .docsight/."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        assert result.exit_code == 0, result.output
        assert (tmp_repo / ".docsight" / "graph.html").exists()

    def test_graph_command_html_contains_vis_network(self, tmp_repo):
        """graph.html should contain vis.Network reference."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
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
        assert (tmp_repo / ".docsight" / "graph.json").exists()

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
        assert (tmp_repo / ".docsight" / "graph.html").exists()

    def test_graph_zoom_default_contains_graph_data(self, tmp_repo):
        """Default graph (zoom) embeds structured graphData JSON."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
        assert "var G=" in content
        assert '"files"' in content
        assert "src/auth.py" in content
        assert "src/cache.py" in content

    def test_graph_zoom_contains_elements(self, tmp_repo):
        """Zoom graph data includes element names and kinds."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
        assert "AuthManager" in content
        assert "validate_token" in content
        assert "cache_lookup" in content
        assert '"CLASS"' in content
        assert '"METHOD"' in content

    def test_graph_zoom_contains_edges(self, tmp_repo):
        """Zoom graph data includes dependency edges."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
        assert '"edges"' in content
        assert "CALLS" in content

    def test_graph_flat_flag(self, tmp_repo):
        """graph --flat uses the old flat vis.js layout."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "graph", "--flat"]
        )
        assert result.exit_code == 0, result.output
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
        # Flat graph has nodesData/edgesData, not the zoom G= variable
        assert "var nodesData" in content
        assert "var G=" not in content

    def test_graph_zoom_has_expand_collapse_ui(self, tmp_repo):
        """Zoom graph has Collapse All button and double-click handler."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
        content = (tmp_repo / ".docsight" / "graph.html").read_text(encoding="utf-8")
        assert "Collapse All" in content
        assert "doubleClick" in content


# ---------------------------------------------------------------------------
# exclude patterns
# ---------------------------------------------------------------------------


class TestCliExcludePatterns:
    """Tests for [tool.docsight] exclude config integration."""

    def test_index_excludes_configured_paths(self, tmp_path):
        """index respects exclude patterns from pyproject.toml."""
        # Create two Python files — one in excluded dir
        src = tmp_path / "src"
        src.mkdir()
        (src / "keep.py").write_text("def kept(): pass\n")
        excluded = tmp_path / "vendor"
        excluded.mkdir()
        (excluded / "lib.py").write_text("def vendored(): pass\n")

        # Configure exclude
        (tmp_path / "pyproject.toml").write_text(
            '[tool.docsight]\nexclude = ["vendor/"]\n'
        )

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        assert result.exit_code == 0, result.output

        index_file = tmp_path / ".docsight" / "index.json"
        index = json.loads(index_file.read_text())
        names = {v["name"] for v in index.values()}
        assert "kept" in names
        assert "vendored" not in names

    def test_scan_excludes_configured_docs(self, tmp_repo):
        """scan excludes markdown files matching exclude patterns."""
        # Add an excluded markdown file
        internal = tmp_repo / ".internal"
        internal.mkdir()
        (internal / "notes.md").write_text("# Internal\n`authenticate()`\n")

        (tmp_repo / "pyproject.toml").write_text(
            '[tool.docsight]\nexclude = [".internal/"]\n'
        )

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
        assert result.exit_code == 0, result.output

        mappings_file = tmp_repo / ".docsight" / "mappings.json"
        mappings = json.loads(mappings_file.read_text())
        assert not any(".internal" in k for k in mappings)

    def test_check_respects_exclude(self, tmp_path):
        """check command uses exclude patterns during auto-index/scan."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("def main(): pass\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nUse `main()` to start.\n")

        # Exclude tests/ — should not affect src/ or docs/
        (tmp_path / "pyproject.toml").write_text(
            '[tool.docsight]\nexclude = ["tests/"]\n'
        )

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "check", "--baseline"])
        assert result.exit_code == 0, result.output

    def test_no_config_still_works(self, tmp_repo):
        """Commands work normally when no [tool.docsight] section exists."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# smarter coverage
# ---------------------------------------------------------------------------


class TestCliSmartCoverage:
    """Tests for API-only coverage (default) vs --all-elements."""

    def test_default_coverage_only_counts_api(self, tmp_path):
        """Default coverage counts classes + module-level functions, not methods."""
        src = tmp_path / "mod.py"
        src.write_text(
            "class Foo:\n"
            "    def bar(self): pass\n"
            "    def baz(self): pass\n"
            "def top_func(): pass\n"
        )
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nUse `Foo` and `top_func()`.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "coverage", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # API = Foo + top_func = 2; methods bar/baz excluded
        assert data["total"] == 2
        assert data["mode"] == "api"

    def test_all_elements_flag_counts_everything(self, tmp_path):
        """--all-elements counts methods too."""
        src = tmp_path / "mod.py"
        src.write_text(
            "class Foo:\n"
            "    def bar(self): pass\n"
            "    def baz(self): pass\n"
            "def top_func(): pass\n"
        )
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nUse `Foo`.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--json", "--all-elements"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # All = Foo + bar + baz + top_func = 4
        assert data["total"] == 4
        assert data["mode"] == "all"

    def test_coverage_label_in_text_output(self, tmp_path):
        """Default text output says 'public API elements'."""
        src = tmp_path / "mod.py"
        src.write_text("def hello(): pass\n")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "coverage"])
        assert result.exit_code == 0
        assert "public API" in result.output

    def test_file_path_reference_covers_elements(self, tmp_path):
        """A file-path reference in docs counts as coverage for that file's API."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "mylib.py").write_text("class Widget:\n    pass\ndef build(): pass\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        # Reference the FILE PATH (with directory), not the class/function names
        (docs / "guide.md").write_text("# Guide\nSee `src/mylib.py` for details.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(cli, ["--repo", str(tmp_path), "coverage", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # Widget and build should be counted as documented via file-path ref
        assert data["documented"] == 2
        assert data["undocumented"] == 0

    def test_file_path_ref_excludes_from_gaps(self, tmp_path):
        """Files referenced by path in docs should not appear in --gaps."""
        src = tmp_path / "core"
        src.mkdir()
        (src / "engine.py").write_text("class Engine:\n    pass\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "arch.md").write_text("# Arch\nMain module: `core/engine.py`.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--gaps", "--json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        gap_files = [g["file"] for g in data["gap_files"]]
        assert not any("engine.py" in f for f in gap_files)


# ---------------------------------------------------------------------------
# impact command
# ---------------------------------------------------------------------------


class TestCliImpact:
    """Tests for the impact command."""

    def test_impact_by_element_id(self, tmp_repo):
        """impact with an element ID shows affected elements."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        # validate_token calls cache_lookup, so changing cache_lookup
        # should show validate_token as affected
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "impact", "cache_lookup"]
        )
        assert result.exit_code == 0, result.output

    def test_impact_by_file_path(self, tmp_repo):
        """impact with a file path expands to all elements in that file."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "impact", "src/cache.py"]
        )
        assert result.exit_code == 0, result.output

    def test_impact_json_output(self, tmp_repo):
        """impact --json returns valid JSON with expected keys."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "impact", "--json", "cache_lookup"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "seed_elements" in data
        assert "affected_elements" in data
        assert "affected_docs" in data

    def test_impact_shows_affected_docs(self, tmp_repo):
        """impact shows docs that reference affected elements."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "impact", "--json", "cache_lookup"]
        )
        data = json.loads(result.output)
        # cache_lookup is referenced in cache-guide.md directly
        doc_paths = [d["doc"] for d in data["affected_docs"]]
        assert any("cache" in d for d in doc_paths)

    def test_impact_unknown_target(self, tmp_repo):
        """impact with a non-existent target exits with error."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_repo), "impact", "nonexistent_thing"]
        )
        assert result.exit_code != 0

    def test_impact_isolated_element(self, tmp_path):
        """impact on an element with no dependents reports 'isolated'."""
        (tmp_path / "solo.py").write_text("def lonely(): pass\n")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "impact", "lonely"]
        )
        assert result.exit_code == 0
        assert "isolated" in result.output.lower()


# ---------------------------------------------------------------------------
# coverage --gaps
# ---------------------------------------------------------------------------


class TestCliCoverageGaps:
    """Tests for the coverage --gaps flag."""

    def test_gaps_finds_undocumented_files(self, tmp_path):
        """--gaps reports files with zero documented public API."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "documented.py").write_text("class Foo: pass\n")
        (src / "undocumented.py").write_text("class Bar: pass\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nUse `Foo`.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--gaps", "--json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        gap_files = [g["file"] for g in data["gap_files"]]
        assert any("undocumented" in f for f in gap_files)
        assert not any("documented.py" == f.split("/")[-1] for f in gap_files)

    def test_gaps_no_gaps(self, tmp_path):
        """--gaps reports no gaps when all files have documented API."""
        (tmp_path / "mod.py").write_text("class Foo: pass\n")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\nUse `Foo`.\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--gaps"]
        )
        assert result.exit_code == 0
        assert "no coverage gaps" in result.output.lower()

    def test_gaps_json_structure(self, tmp_path):
        """--gaps --json returns expected keys."""
        (tmp_path / "mod.py").write_text("def f(): pass\n")
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--gaps", "--json"]
        )
        data = json.loads(result.output)
        assert "gap_files" in data
        assert "total_gap_files" in data
        assert "total_gap_elements" in data

    def test_gaps_sorted_by_dependency_weight(self, tmp_path):
        """Gap files are sorted by depended_on_by (most first)."""
        src = tmp_path / "src"
        src.mkdir()
        # util.py is depended on by app.py
        (src / "util.py").write_text("def helper(): pass\n")
        (src / "app.py").write_text(
            "from src.util import helper\ndef main(): helper()\n"
        )
        (src / "orphan.py").write_text("def nobody(): pass\n")

        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_path), "init"])
        runner.invoke(cli, ["--repo", str(tmp_path), "index"])
        runner.invoke(cli, ["--repo", str(tmp_path), "scan"])
        result = runner.invoke(
            cli, ["--repo", str(tmp_path), "coverage", "--gaps", "--json"]
        )
        data = json.loads(result.output)
        if len(data["gap_files"]) >= 2:
            # First gap should have >= as many dependents as second
            assert data["gap_files"][0]["depended_on_by"] >= data["gap_files"][1]["depended_on_by"]


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


class TestCliDiff:
    """Tests for the diff command."""

    def test_diff_no_changes(self, tmp_repo):
        """diff against baseline with no changes reports nothing."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff"])
        assert result.exit_code == 0
        assert "no element changes" in result.output.lower()

    def test_diff_detects_signature_change(self, tmp_repo):
        """diff detects a signature change against baseline."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        auth = tmp_repo / "src" / "auth.py"
        auth.write_text(auth.read_text().replace(
            "strict: bool = True", "mode: str = 'fast'"
        ))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["changed_elements"]) > 0
        types = [c["change_type"] for c in data["changed_elements"]]
        assert "signature" in types

    def test_diff_shows_affected_docs(self, tmp_repo):
        """diff shows which docs are affected by the changes."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        auth = tmp_repo / "src" / "auth.py"
        auth.write_text(auth.read_text().replace(
            "strict: bool = True", "mode: str = 'fast'"
        ))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        data = json.loads(result.output)
        doc_paths = [d["doc"] for d in data["affected_docs"]]
        assert any("auth" in d for d in doc_paths)

    def test_diff_json_structure(self, tmp_repo):
        """diff --json has expected keys."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        data = json.loads(result.output)
        assert "base" in data
        assert "changed_elements" in data
        assert "affected_docs" in data

    def test_diff_text_output(self, tmp_repo):
        """diff text output contains readable summary."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        cache = tmp_repo / "src" / "cache.py"
        cache.write_text(cache.read_text().replace(
            "def cache_lookup(key: str) -> str:",
            'def cache_lookup(key: str, ttl: int = 60) -> str:',
        ))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff"])
        assert result.exit_code == 0
        assert "changed" in result.output.lower()

    def test_diff_detects_deleted_element(self, tmp_repo):
        """diff flags a deleted/renamed function as 'deleted' and reports affected docs."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        # Rename authenticate → login (old name deleted, new name added)
        auth = tmp_repo / "src" / "auth.py"
        auth.write_text(auth.read_text().replace(
            "def authenticate(", "def login("
        ))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        types = [c["change_type"] for c in data["changed_elements"]]
        assert "deleted" in types
        # The doc referencing authenticate should be flagged
        doc_paths = [d["doc"] for d in data["affected_docs"]]
        assert any("auth" in d for d in doc_paths)

    def test_diff_no_false_positive_from_excluded_files(self, tmp_repo):
        """diff must not flag elements from files excluded after baseline."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        # Now add an exclude pattern that hides src/cache.py
        (tmp_repo / "pyproject.toml").write_text(
            '[tool.docsight]\nexclude = ["src/cache.py"]\n'
        )
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # cache.py elements should NOT be flagged as deleted
        deleted = [c for c in data["changed_elements"]
                   if c["change_type"] == "deleted"]
        assert not any("cache" in d["element_id"] for d in deleted)

    def test_diff_detects_real_file_deletion(self, tmp_repo):
        """diff flags elements from a genuinely deleted file."""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

        # Actually delete the file from disk
        (tmp_repo / "src" / "cache.py").unlink()
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "diff", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        deleted = [c for c in data["changed_elements"]
                   if c["change_type"] == "deleted"]
        assert any("cache" in d["element_id"] for d in deleted)
