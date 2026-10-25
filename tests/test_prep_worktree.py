import fcntl
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
CLI = REPO_ROOT / ".agents/skills/prep-worktree/scripts/prep-worktree"


def git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def git_out(path: Path, *args: str) -> str:
    return git(path, *args).stdout.strip()


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    origin = tmp_path / f"{name}-origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    repo = tmp_path / name
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    return repo


def common_dir(repo: Path) -> str:
    return git_out(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")


def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config" / "smarter-way" / "config.json"


def write_config(tmp_path: Path, data: dict) -> None:
    path = config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def base_env(tmp_path: Path, owner: str = "test-session") -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PREP_WORKTREE_PROTECTED_DEV_PATH", None)
    env.pop("PREP_WORKTREE_MAX", None)
    env.update(
        {
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "PREP_WORKTREE_ROOT": str(tmp_path / "worktrees"),
            "PREP_WORKTREE_OWNER": owner,
            "OPENCODE_SESSION_ID": owner,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    return env


def run_cli(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env or os.environ.copy(),
    )


def acquire(repo: Path, env: dict[str, str], *extra: str) -> dict:
    result = run_cli(repo, "acquire", "--json", *extra, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def state_dir(repo: Path) -> Path:
    return Path(common_dir(repo)) / "prep-worktree"


def record_path(repo: Path, admin_id: str) -> Path:
    return state_dir(repo) / "worktrees" / admin_id


def expire(repo: Path, admin_id: str) -> None:
    lease_path = record_path(repo, admin_id) / "lease.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["last_seen"] = 0
    lease_path.write_text(json.dumps(lease), encoding="utf-8")


def test_two_repos_with_dirty_protected_checkouts(tmp_path: Path) -> None:
    repo_a = make_repo(tmp_path, "a")
    repo_b = make_repo(tmp_path, "b")
    (repo_a / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    write_config(
        tmp_path,
        {
            "prep_worktree": {
                "repos": {
                    common_dir(repo_a): {"protected_paths": [str(repo_a)]},
                    common_dir(repo_b): {"protected_paths": [str(repo_b)]},
                }
            }
        },
    )
    env = base_env(tmp_path)
    first = acquire(repo_a, env)
    second = acquire(repo_b, env)
    assert first["path"] != second["path"]
    assert not Path(first["path"]).is_relative_to(repo_a)
    assert not Path(second["path"]).is_relative_to(repo_b)


def test_missing_wrong_repo_and_dirty_protected_paths_do_not_block(tmp_path: Path) -> None:
    repo_a = make_repo(tmp_path, "a")
    repo_b = make_repo(tmp_path, "b")
    (repo_a / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    write_config(
        tmp_path,
        {
            "prep_worktree": {
                "repos": {
                    common_dir(repo_a): {
                        "protected_paths": [
                            str(tmp_path / "missing"),
                            str(repo_b),
                            str(repo_a),
                        ]
                    }
                }
            }
        },
    )
    result = run_cli(repo_a, "acquire", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "PROTECTED_MISSING" in result.stderr
    assert "PROTECTED_OTHER_REPO" in result.stderr
    assert "PROTECTED_DIRTY" in result.stderr


def test_ignored_files_do_not_block(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text("logs/\n.venv/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-m", "ignore")
    (repo / "logs").mkdir()
    (repo / "logs" / "run.log").write_text("noise\n", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "marker").write_text("cache\n", encoding="utf-8")
    write_config(
        tmp_path,
        {"prep_worktree": {"repos": {common_dir(repo): {"protected_paths": [str(repo)]}}}},
    )
    result = run_cli(repo, "acquire", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "PROTECTED_DIRTY" not in result.stderr


def test_base_fetch_failure_uses_existing_ref(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing-origin.git"))
    result = run_cli(repo, "acquire", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "BASE_STALE" in result.stderr


def test_per_repo_config_selects_protected_paths(tmp_path: Path) -> None:
    repo_a = make_repo(tmp_path, "a")
    repo_b = make_repo(tmp_path, "b")
    write_config(
        tmp_path,
        {
            "prep_worktree": {
                "defaults": {"protected_paths": [str(repo_a)]},
                "repos": {common_dir(repo_b): {"protected_paths": [str(repo_b)]}},
            }
        },
    )
    result = run_cli(repo_b, "status", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["protected_paths"] == [str(repo_b)]


def test_acquire_returns_unique_paths(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: run_cli(repo, "acquire", "--json", env=env), range(8))
        )
    assert all(result.returncode == 0 for result in results), [
        result.stderr for result in results if result.returncode != 0
    ]
    paths = {json.loads(result.stdout)["path"] for result in results}
    assert len(paths) == 8


def test_guard_rejects_foreign_worktree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    first = acquire(repo, env)
    second = acquire(repo, env)
    result = run_cli(
        Path(first["path"]),
        "guard",
        "--id",
        second["id"],
        env=env,
    )
    assert result.returncode == 2
    assert "foreign worktree" in result.stderr


def test_guard_rejects_missing_lease(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run_cli(
        repo,
        "guard",
        "--id",
        "missing",
        env=base_env(tmp_path),
    )
    assert result.returncode == 2
    assert "no lease" in result.stderr


def test_heartbeat_and_release_are_owner_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    record = acquire(repo, env)
    other = base_env(tmp_path, owner="other")
    heartbeat = run_cli(
        Path(record["path"]), "heartbeat", "--id", record["id"], env=other
    )
    assert heartbeat.returncode == 2
    release = run_cli(
        Path(record["path"]), "release", "--id", record["id"], env=other
    )
    assert release.returncode == 2
    released = run_cli(
        Path(record["path"]), "release", "--id", record["id"], env=env
    )
    assert released.returncode == 0, released.stderr
    assert "idle" in released.stdout


def test_lease_records_survive_git_gc(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    record = acquire(repo, base_env(tmp_path))
    git(repo, "gc")
    assert (record_path(repo, record["id"]) / "meta.json").exists()
    assert (record_path(repo, record["id"]) / "lease.json").exists()


def test_reap_removes_clean_expired_worktree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    record = acquire(repo, env)
    expire(repo, record["id"])
    result = run_cli(repo, "reap", "--apply", "--json", env=env)
    assert result.returncode == 0, result.stderr
    actions = json.loads(result.stdout)["actions"]
    assert actions[0]["action"] == "REMOVE"
    assert not Path(record["path"]).exists()
    lease = json.loads((record_path(repo, record["id"]) / "lease.json").read_text())
    assert lease["state"] == "archived"


def test_reap_archives_dirty_worktree_before_removal(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    record = acquire(repo, env)
    path = Path(record["path"])
    (path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (path / "new-file.txt").write_text("new\n", encoding="utf-8")
    expire(repo, record["id"])
    result = run_cli(repo, "reap", "--apply", "--json", env=env)
    assert result.returncode == 0, result.stderr
    action = json.loads(result.stdout)["actions"][0]
    assert action["action"] == "ARCHIVE_REMOVE"
    assert not path.exists()
    ref = action["archive_ref"]
    assert git(repo, "cat-file", "-t", ref).stdout.strip() == "commit"
    assert git(repo, "show", f"{ref}:new-file.txt").stdout == "new\n"


def test_reap_skips_active_and_locked_worktrees(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    record = acquire(repo, env)
    path = Path(record["path"])
    process = subprocess.Popen(["sleep", "30"], cwd=path)
    try:
        expire(repo, record["id"])
        result = run_cli(repo, "reap", "--apply", "--json", env=env)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["actions"][0]["action"] == "SKIP_ACTIVE"
        assert path.exists()
    finally:
        process.kill()
        process.wait()
    git(repo, "worktree", "lock", str(path))
    result = run_cli(repo, "reap", "--apply", "--json", env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["actions"][0]["action"] == "SKIP_LOCKED"


def test_reap_refuses_secret_ignored_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    record = acquire(repo, env)
    path = Path(record["path"])
    (path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    expire(repo, record["id"])
    result = run_cli(repo, "reap", "--apply", "--json", env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["actions"][0]["action"] == "HUMAN_REVIEW"
    assert path.exists()


def test_reuse_resets_tracked_files_and_keeps_ignored_cache(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-m", "ignore")
    git(repo, "push", "origin", "main")
    env = base_env(tmp_path)
    first = acquire(repo, env)
    first_path = Path(first["path"])
    released = run_cli(first_path, "release", "--id", first["id"], env=env)
    assert released.returncode == 0, released.stderr
    (first_path / ".venv").mkdir()
    (first_path / ".venv" / "cache").write_text("keep\n", encoding="utf-8")
    second = acquire(repo, env)
    assert second["path"] == first["path"]
    assert second["branch"] != first["branch"]
    assert (
        git(repo, "show-ref", "--verify", f"refs/heads/{first['branch']}", check=False).returncode
        != 0
    )
    assert (Path(second["path"]) / ".venv" / "cache").exists()
    assert (Path(second["path"]) / "tracked.txt").read_text() == "base\n"


def test_reap_lock_busy_does_not_block_acquire(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_config(
        tmp_path,
        {
            "prep_worktree": {
                "defaults": {
                    "max_managed_worktrees": 1,
                    "idle_ttl_hours": 0,
                }
            }
        },
    )
    env = base_env(tmp_path)
    acquire(repo, env)
    lock_path = state_dir(repo) / "reap.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_cli(repo, "acquire", "--json", env=env)
        assert result.returncode == 0, result.stderr
        assert "REAP_SKIPPED" in result.stderr
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def make_legacy_worktree(tmp_path: Path, repo: Path) -> Path:
    path = tmp_path / ".repo-prep-legacy"
    git(repo, "worktree", "add", "-b", "prep-worktree/legacy", str(path), "main")
    return path


def test_adopt_dry_run_changes_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    legacy = make_legacy_worktree(tmp_path, repo)
    before = git_out(repo, "worktree", "list", "--porcelain")
    result = run_cli(repo, "adopt", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["managed_legacy"][0]["path"] == str(legacy)
    assert record_path(repo, "legacy").exists() is False
    assert git_out(repo, "worktree", "list", "--porcelain") == before


def test_adopt_skips_user_owned_worktree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    user = tmp_path / "user-worktree"
    git(repo, "worktree", "add", "-b", "feature/user", str(user), "main")
    result = run_cli(repo, "adopt", "--apply", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["managed_legacy"] == []
    assert str(user) in data["user_owned"]
    assert not list((state_dir(repo) / "worktrees").glob("*"))


def test_adopt_detects_legacy_prep_branch(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    legacy = make_legacy_worktree(tmp_path, repo)
    result = run_cli(repo, "adopt", "--apply", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["managed_legacy"][0]["path"] == str(legacy)
    records = list((state_dir(repo) / "worktrees").glob("*/meta.json"))
    assert records


def test_prunable_registration_is_reconciled(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    legacy = make_legacy_worktree(tmp_path, repo)
    shutil.rmtree(legacy)
    result = run_cli(repo, "adopt", "--apply", "--json", env=base_env(tmp_path))
    assert result.returncode == 0, result.stderr
    prunable = json.loads(result.stdout)["prunable"]
    assert any(item["path"] == str(legacy) for item in prunable)
    listed = git_out(repo, "worktree", "list", "--porcelain")
    assert not any(line.startswith("prunable") for line in listed.splitlines())
    assert git(repo, "show-ref", "--verify", "refs/heads/prep-worktree/legacy").returncode == 0


def test_readme_config_example_parses() -> None:
    data = json.loads((REPO_ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert "prep_worktree" in data


def test_doctor_reports_clean_fixture(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    env = base_env(tmp_path)
    acquire(repo, env)
    result = run_cli(repo, "doctor", "--json", env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
