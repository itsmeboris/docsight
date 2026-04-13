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
