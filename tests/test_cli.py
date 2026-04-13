"""Tests for doc_updater.cli."""

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
