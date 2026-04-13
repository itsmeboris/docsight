"""End-to-end integration tests."""
import json
from click.testing import CliRunner
from doc_updater.cli import cli


class TestE2E:
    def test_e2e_direct_staleness(self, tmp_repo):
        """baseline → change signature → check detects stale"""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        # Change validate_token signature
        auth = tmp_repo / "src" / "auth.py"
        auth.write_text(auth.read_text().replace("strict: bool = True", "mode: str = 'fast'"))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
        assert result.exit_code == 1

    def test_e2e_transitive_staleness(self, tmp_repo):
        """baseline → change cache_lookup signature → check detects transitive"""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        # Change cache_lookup (called by validate_token, referenced in auth-guide.md)
        cache = tmp_repo / "src" / "cache.py"
        cache.write_text(cache.read_text().replace(
            'def cache_lookup(key: str) -> str:',
            'def cache_lookup(key: str, default: str = "") -> str:',
        ))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
        data = json.loads(result.output)
        stale_docs = [d["doc"] for d in data.get("stale_docs", [])]
        assert any("auth" in d for d in stale_docs)

    def test_e2e_no_false_positive_on_comment_change(self, tmp_repo):
        """Adding a comment should NOT trigger staleness (body_hash uses ast.dump)"""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        auth = tmp_repo / "src" / "auth.py"
        auth.write_text("# New comment at top\n" + auth.read_text())
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
        data = json.loads(result.output)
        assert data["summary"]["stale"] == 0

    def test_e2e_renamed_function_detected(self, tmp_repo):
        """Renamed symbol should be flagged as stale"""
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        auth = tmp_repo / "src" / "auth.py"
        auth.write_text(auth.read_text().replace("def authenticate(", "def login("))
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
        assert result.exit_code == 1

    def test_e2e_full_flow_json(self, tmp_repo):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
        data = json.loads(result.output)
        assert data["summary"]["total"] >= 2
        assert data["summary"]["healthy"] >= 2

    def test_e2e_status_after_baseline(self, tmp_repo):
        runner = CliRunner()
        runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
        runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
        result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
        assert result.exit_code == 0
        assert "healthy" in result.output.lower() or "doc" in result.output.lower()
