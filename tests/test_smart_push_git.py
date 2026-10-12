import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".agents/skills/smart-push-to-prod/scripts/smart_push_git.py"


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class SmartPushGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bare = self.root / "origin.git"
        self.repo = self.root / "develop"
        self.prod = self.root / "prod"
        self.home = self.root / "home"
        self.home.mkdir()
        run_git(self.root, "init", "--bare", str(self.bare))
        run_git(self.root, "init", str(self.repo))
        run_git(self.repo, "config", "user.email", "test@example.com")
        run_git(self.repo, "config", "user.name", "Test User")
        (self.repo / "state.txt").write_text("A\n", encoding="utf-8")
        run_git(self.repo, "add", "state.txt")
        run_git(self.repo, "commit", "-m", "initial")
        run_git(self.repo, "branch", "-M", "main")
        run_git(self.repo, "remote", "add", "origin", str(self.bare))
        run_git(self.repo, "push", "-u", "origin", "main")
        run_git(self.bare, "symbolic-ref", "HEAD", "refs/heads/main")
        run_git(self.root, "clone", str(self.bare), str(self.prod))
        run_git(self.prod, "config", "user.email", "test@example.com")
        run_git(self.prod, "config", "user.name", "Test User")
        self.env = os.environ.copy()
        self.env["SMART_PUSH_PROD_PATH"] = f"{self.repo}={self.prod}"
        login_config = f"export SMART_PUSH_PROD_PATH='{self.repo}={self.prod}'\n"
        for name in (".bash_profile", ".bashrc", "bash_env"):
            (self.home / name).write_text(login_config, encoding="utf-8")
        self.env["HOME"] = str(self.home)
        self.env["BASH_ENV"] = str(self.home / "bash_env")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_helper(
        self,
        *args: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        runner = os.environ.get("SMART_PUSH_HELPER_RUNNER", "python3")
        return subprocess.run(
            [*shlex.split(runner), str(SCRIPT), *args],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            env=env or self.env,
        )

    def set_login_mapping(self, mapping: str) -> None:
        self.env["SMART_PUSH_PROD_PATH"] = mapping
        login_config = f"export SMART_PUSH_PROD_PATH='{mapping}'\n"
        for name in (".bash_profile", ".bashrc", "bash_env"):
            (self.home / name).write_text(login_config, encoding="utf-8")

    def set_prod_mapping(self, develop: Path, prod: Path) -> None:
        self.set_login_mapping(f"{develop}={prod}")

    def write_fake_gh_raw(self, output: str) -> None:
        fake_bin = self.root / "bin"
        fake_bin.mkdir(exist_ok=True)
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = repo ] && [ \"$2\" = view ]; then\n"
            "  printf '%s\\n' '{\"nameWithOwner\":\"test/test\"}'\n"
            "else\n"
            "  printf '%s\\n' "
            + shlex.quote(output)
            + "\nfi\n",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"

    def write_fake_gh(self, payload: dict[str, object]) -> None:
        payload = {
            "baseRefName": "main",
            "url": "https://github.com/test/test/pull/1",
            **payload,
        }
        self.write_fake_gh_raw(json.dumps(payload))

    def test_preflight_reports_default_and_prod_mapping(self) -> None:
        result = self.run_helper("preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["default"], "main")
        self.assertEqual(data["prod"], str(self.prod.resolve()))
        self.assertEqual(data["ahead"], 0)

    def test_preflight_reports_secret_paths(self) -> None:
        (self.repo / ".env").write_text("TOKEN=private\n", encoding="utf-8")

        result = self.run_helper("preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["secret_paths"], [".env"])

    def test_preflight_reports_secret_rename_endpoints(self) -> None:
        (self.repo / ".env").write_text("TOKEN=private\n", encoding="utf-8")
        run_git(self.repo, "add", ".env")
        run_git(self.repo, "commit", "-m", "seed secret path")
        run_git(self.repo, "mv", ".env", "safe-name.txt")

        result = self.run_helper("preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".env", json.loads(result.stdout)["secret_paths"])

    def test_preflight_rejects_non_git_checkout(self) -> None:
        result = self.run_helper("preflight", cwd=self.root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a git checkout", result.stderr)

    def test_preflight_rejects_missing_default_ref(self) -> None:
        empty_origin = self.root / "empty-origin.git"
        run_git(self.root, "init", "--bare", str(empty_origin))
        run_git(self.repo, "remote", "set-url", "origin", str(empty_origin))
        run_git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no origin/main or origin/master ref", result.stderr)

    def test_preflight_rejects_missing_origin(self) -> None:
        run_git(self.repo, "remote", "remove", "origin")

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote origin is not configured", result.stderr)

    def test_preflight_rejects_running_from_mapped_prod_checkout(self) -> None:
        self.set_prod_mapping(self.prod, self.repo)

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("current checkout is mapped as prod", result.stderr)

    def test_preflight_reports_missing_mapped_prod_checkout(self) -> None:
        missing_prod = self.root / "missing-prod"
        self.set_prod_mapping(self.repo, missing_prod)

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mapped prod checkout is not a git checkout", result.stderr)

    def test_preflight_rejects_relative_prod_mapping(self) -> None:
        self.set_login_mapping("relative=prod")

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("paths must be absolute", result.stderr)

    def test_preflight_rejects_malformed_prod_mapping(self) -> None:
        self.set_login_mapping("malformed")

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid SMART_PUSH_PROD_PATH pair", result.stderr)

    def test_preflight_rejects_multiple_prod_mappings(self) -> None:
        second_prod = self.root / "second-prod"
        run_git(self.root, "clone", str(self.bare), str(second_prod))
        self.set_login_mapping(f"{self.repo}={self.prod};{self.repo}={second_prod}")

        result = self.run_helper("preflight")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple prod checkouts map this repository", result.stderr)

    def test_preflight_ignores_mapping_for_another_repository(self) -> None:
        other_develop = self.root / "other-develop"
        other_prod = self.root / "other-prod"
        run_git(self.root, "clone", str(self.bare), str(other_develop))
        run_git(self.root, "clone", str(self.bare), str(other_prod))
        self.set_prod_mapping(other_develop, other_prod)

        result = self.run_helper("preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["prod"], "")

    def test_branch_sync_creates_feature_branch_from_default(self) -> None:
        other = self.root / "other"
        run_git(self.root, "clone", str(self.bare), str(other))
        run_git(other, "config", "user.email", "test@example.com")
        run_git(other, "config", "user.name", "Test User")
        (other / "state.txt").write_text("remote update\n", encoding="utf-8")
        run_git(other, "add", "state.txt")
        run_git(other, "commit", "-m", "remote update")
        run_git(other, "push", "origin", "HEAD:main")

        result = self.run_helper("branch-sync", "--branch", "feature/test-sync")

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["action"], "created")
        self.assertEqual(data["branch"], "feature/test-sync")
        self.assertEqual(run_git(self.repo, "branch", "--show-current"), "feature/test-sync")
        self.assertEqual(
            (self.repo / "state.txt").read_text(encoding="utf-8"),
            "remote update\n",
        )

    def test_branch_sync_requires_branch_name_on_default(self) -> None:
        result = self.run_helper("branch-sync")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--branch is required", result.stderr)

    def test_branch_sync_rejects_detached_head(self) -> None:
        run_git(self.repo, "checkout", "--detach")

        result = self.run_helper("branch-sync")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("detached HEAD", result.stderr)

    def test_branch_sync_merges_default_into_existing_feature_branch(self) -> None:
        run_git(self.repo, "checkout", "-b", "feature/existing")
        other = self.root / "other"
        run_git(self.root, "clone", str(self.bare), str(other))
        run_git(other, "config", "user.email", "test@example.com")
        run_git(other, "config", "user.name", "Test User")
        (other / "state.txt").write_text("remote update\n", encoding="utf-8")
        run_git(other, "add", "state.txt")
        run_git(other, "commit", "-m", "remote update")
        run_git(other, "push", "origin", "HEAD:main")

        result = self.run_helper("branch-sync")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["action"], "kept")
        self.assertEqual(run_git(self.repo, "branch", "--show-current"), "feature/existing")
        self.assertEqual(
            (self.repo / "state.txt").read_text(encoding="utf-8"),
            "remote update\n",
        )

    def test_unmerged_pr_prevents_checkout_refresh(self) -> None:
        self.write_fake_gh(
            {"state": "OPEN", "mergedAt": None, "mergeCommit": None}
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no checkout will be refreshed", result.stderr)
        self.assertEqual(run_git(self.repo, "branch", "--show-current"), "main")

    def test_refresh_uses_primary_default_worktree_from_linked_worktree(self) -> None:
        linked = self.root / "linked"
        run_git(self.repo, "worktree", "add", "-b", "feature/linked", str(linked))
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper(
            "refresh",
            "--pr-url",
            "https://example.test/pr/1",
            cwd=linked,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_git(linked, "branch", "--show-current"), "feature/linked")
        self.assertEqual(run_git(self.repo, "branch", "--show-current"), "main")

    def test_refresh_rejects_dirty_primary_worktree(self) -> None:
        run_git(self.repo, "checkout", "-b", "feature/dirty")
        (self.repo / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("default refresh checkout is dirty", result.stderr)
        self.assertEqual(run_git(self.repo, "branch", "--show-current"), "feature/dirty")

    def test_refresh_rejects_prod_checkout_on_non_default_branch(self) -> None:
        run_git(self.prod, "checkout", "-b", "release")
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prod checkout is on", result.stderr)

    def test_refresh_reads_documented_bashrc_mapping_without_inherited_env(self) -> None:
        bashrc_home = self.root / "bashrc-only-home"
        bashrc_home.mkdir()
        (bashrc_home / ".bashrc").write_text(
            f"export SMART_PUSH_PROD_PATH='{self.repo}={self.prod}'\n",
            encoding="utf-8",
        )
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )
        env = self.env.copy()
        env.pop("SMART_PUSH_PROD_PATH", None)
        env["HOME"] = str(bashrc_home)
        env.pop("BASH_ENV", None)

        result = self.run_helper(
            "refresh",
            "--pr-url",
            "https://example.test/pr/1",
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["prod"], str(self.prod.resolve()))

    def test_invalid_pr_json_prevents_checkout_refresh(self) -> None:
        self.write_fake_gh_raw("not-json")

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gh returned invalid PR JSON", result.stderr)

    def test_refresh_requires_all_merge_metadata(self) -> None:
        invalid_payloads = (
            {"state": "OPEN", "mergedAt": None, "mergeCommit": None},
            {"state": "MERGED", "mergedAt": None, "mergeCommit": {"oid": "remote"}},
            {"state": "MERGED", "mergedAt": "2026-10-06T00:00:00Z", "mergeCommit": None},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.write_fake_gh(payload)
                result = self.run_helper(
                    "refresh", "--pr-url", "https://example.test/pr/1"
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("no checkout will be refreshed", result.stderr)
                self.assertEqual(run_git(self.repo, "branch", "--show-current"), "main")

    def test_refresh_rejects_wrong_pr_repository_or_base(self) -> None:
        invalid_payloads = (
            {
                "url": "https://github.com/other/repository/pull/1",
            },
            {"baseRefName": "release"},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.write_fake_gh(
                    {
                        "state": "MERGED",
                        "mergedAt": "2026-10-06T00:00:00Z",
                        "mergeCommit": {"oid": "remote"},
                        **payload,
                    }
                )
                result = self.run_helper(
                    "refresh", "--pr-url", "https://example.test/pr/1"
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("does not target this repository", result.stderr)
                self.assertEqual(run_git(self.repo, "branch", "--show-current"), "main")

    def test_bashrc_command_substitution_is_not_executed(self) -> None:
        marker = self.root / "executed-marker"
        bashrc_home = self.root / "unsafe-bashrc-home"
        bashrc_home.mkdir()
        (bashrc_home / ".bashrc").write_text(
            "export SMART_PUSH_PROD_PATH=\"$(touch "
            + str(marker)
            + ")\"\n",
            encoding="utf-8",
        )
        env = self.env.copy()
        env.pop("SMART_PUSH_PROD_PATH", None)
        env["HOME"] = str(bashrc_home)
        env.pop("BASH_ENV", None)

        result = self.run_helper("preflight", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(json.loads(result.stdout)["prod"], "")

    def test_preflight_reports_secret_content_in_ordinary_filename(self) -> None:
        (self.repo / "settings.txt").write_text(
            "API_KEY = " + '"ordinary-' + "secret-value-12345\"\n",
            encoding="utf-8",
        )

        result = self.run_helper("preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "content:settings.txt", json.loads(result.stdout)["secret_paths"]
        )

    def test_refresh_rejects_dirty_prod_before_local_refresh(self) -> None:
        (self.prod / "state.txt").write_text("local prod change\n", encoding="utf-8")
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )
        local_head = run_git(self.repo, "rev-parse", "HEAD")

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prod checkout is dirty", result.stderr)
        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD"), local_head)

    def test_prod_pull_failure_is_reported_after_local_refresh(self) -> None:
        (self.prod / "state.txt").write_text("local prod update\n", encoding="utf-8")
        run_git(self.prod, "add", "state.txt")
        run_git(self.prod, "commit", "-m", "local prod divergence")

        other = self.root / "other"
        run_git(self.root, "clone", str(self.bare), str(other))
        run_git(other, "config", "user.email", "test@example.com")
        run_git(other, "config", "user.name", "Test User")
        (other / "state.txt").write_text("remote update\n", encoding="utf-8")
        run_git(other, "add", "state.txt")
        run_git(other, "commit", "-m", "remote squash result")
        run_git(other, "push", "origin", "HEAD:main")
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["local_pull"], "ok")
        self.assertEqual(data["prod_pull"], "error")

    def test_refresh_without_prod_mapping_reports_skipped_prod(self) -> None:
        self.set_login_mapping("")
        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["local_pull"], "ok")
        self.assertEqual(data["prod_pull"], "skipped")

    def test_local_ff_only_failure_does_not_block_prod_refresh(self) -> None:
        (self.repo / "state.txt").write_text("B\n", encoding="utf-8")
        run_git(self.repo, "add", "state.txt")
        run_git(self.repo, "commit", "-m", "local divergence")
        run_git(self.repo, "checkout", "-b", "local-only")

        other = self.root / "other"
        run_git(self.root, "clone", str(self.bare), str(other))
        run_git(other, "config", "user.email", "test@example.com")
        run_git(other, "config", "user.name", "Test User")
        (other / "state.txt").write_text("C\n", encoding="utf-8")
        run_git(other, "add", "state.txt")
        run_git(other, "commit", "-m", "remote squash result")
        remote_sha = run_git(other, "rev-parse", "HEAD")
        run_git(other, "push", "origin", "HEAD:main")

        self.write_fake_gh(
            {
                "state": "MERGED",
                "mergedAt": "2026-10-06T00:00:00Z",
                "mergeCommit": {"oid": "remote"},
            }
        )

        result = self.run_helper("refresh", "--pr-url", "https://example.test/pr/1")

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["local_pull"], "error")
        self.assertEqual(data["prod_pull"], "ok")
        self.assertEqual(run_git(self.prod, "rev-parse", "HEAD"), remote_sha)


if __name__ == "__main__":
    unittest.main()
