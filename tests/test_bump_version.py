"""Exercise releases with real temporary Git repositories and a fake GitHub CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "bump_version.sh"
MANIFEST = "custom_components/hikvision_access_control/manifest.json"


def command(cwd, *args, env=None, check=True):
    return subprocess.run(
        args, cwd=cwd, env=env, text=True, capture_output=True, check=check
    )


@pytest.fixture
def release_repo(tmp_path):
    repo = tmp_path / "project with spaces"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GH_TEST_RESULT": str(tmp_path / "release.json"),
    }
    command(tmp_path, "git", "init", "--bare", str(remote), env=env)
    command(repo, "git", "init", "-b", "main", env=env)
    command(repo, "git", "config", "user.email", "release@example.test", env=env)
    command(repo, "git", "config", "user.name", "Release test", env=env)
    command(repo, "git", "remote", "add", "origin", str(remote), env=env)
    shutil.copy2(SCRIPT, repo / "bump_version.sh")
    manifest = repo / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"domain": "hikvision_access_control", "version": "0.1.4"}\n')
    (repo / "hacs.json").write_text("{}\n")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n"
        "- Preserve event details.\n\n## [0.1.4] - 2026-09-08\n\n- Previous release.\n"
    )
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.ruff_cache/\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text("def test_smoke():\n    pass\n")
    command(repo, "git", "add", ".", env=env)
    command(repo, "git", "commit", "-m", "Initial code", env=env)
    command(repo, "git", "push", "-u", "origin", "main", env=env)

    binaries = tmp_path / "bin"
    binaries.mkdir()
    gh = binaries / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['auth', 'status']:\n"
        "    sys.exit(0)\n"
        "if args[:2] == ['repo', 'view']:\n"
        "    print('example/hikvision-access-control')\n"
        "elif args[:2] == ['release', 'create']:\n"
        "    if os.environ.get('GH_TEST_FAIL'):\n"
        "        sys.exit(1)\n"
        "    notes = Path(args[args.index('--notes-file') + 1]).read_text()\n"
        "    result = json.dumps({'args': args, 'notes': notes})\n"
        "    Path(os.environ['GH_TEST_RESULT']).write_text(result)\n"
        "else:\n"
        "    sys.exit('Unexpected gh invocation: ' + repr(args))\n"
    )
    gh.chmod(0o755)
    uv = binaries / "uv"
    uv.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['UV_TEST_RESULT']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UV_TEST_MARKER']).touch()\n"
    )
    uv.chmod(0o755)
    env["PATH"] = f"{binaries}{os.pathsep}{env['PATH']}"
    env["UV_TEST_RESULT"] = str(tmp_path / "uv.json")
    env["UV_TEST_MARKER"] = str(tmp_path / "dependencies-installed")
    return repo, remote, env


@pytest.mark.parametrize(
    ("bump", "expected"),
    [("patch", "0.1.5"), ("minor", "0.2.0"), ("major", "1.0.0"), ("0.3.2", "0.3.2")],
)
def test_dry_run_does_not_change_files_or_publish(release_repo, bump, expected):
    repo, _, env = release_repo
    # A preview must also work before the user's changes have been committed.
    (repo / "pending.txt").write_text("Uncommitted work")
    before = command(repo, "git", "status", "--porcelain", env=env).stdout
    result = command(repo, "bash", "bump_version.sh", bump, "--dry-run", env=env)
    assert f"0.1.4 -> {expected}" in result.stdout
    assert command(repo, "git", "status", "--porcelain", env=env).stdout == before
    assert json.loads((repo / MANIFEST).read_text())["version"] == "0.1.4"
    assert not Path(env["GH_TEST_RESULT"]).exists()


def test_release_updates_versions_pushes_tag_and_publishes_notes(release_repo):
    repo, remote, env = release_repo
    command(repo, "bash", "bump_version.sh", env=env)
    assert json.loads((repo / MANIFEST).read_text())["version"] == "0.1.5"
    changelog = (repo / "CHANGELOG.md").read_text()
    assert "## [Unreleased]\n\n## [0.1.5] - " in changelog
    assert "## [0.1.4] - 2026-09-08" in changelog
    assert command(repo, "git", "status", "--porcelain", env=env).stdout == ""
    assert (
        command(repo, "git", "cat-file", "-t", "v0.1.5", env=env).stdout.strip()
        == "tag"
    )
    commit = command(repo, "git", "rev-parse", "HEAD", env=env).stdout
    for ref in ("refs/heads/main", "refs/tags/v0.1.5^{}"):
        assert command(remote, "git", "rev-parse", ref, env=env).stdout == commit
    changed = command(
        repo, "git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", env=env
    )
    assert set(changed.stdout.splitlines()) == {MANIFEST, "CHANGELOG.md"}
    release = json.loads(Path(env["GH_TEST_RESULT"]).read_text())
    assert release["args"][2] == "v0.1.5"
    assert "--verify-tag" in release["args"]
    assert release["notes"] == "### Fixed\n\n- Preserve event details.\n"


def test_release_installs_missing_dependencies_with_uv(release_repo):
    repo, _, env = release_repo
    python_wrapper = Path(env["UV_TEST_RESULT"]).parent / "bin" / "missing-deps-python"
    python_wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "dependency_check = sys.argv[1:] == "
        "['-c', 'import pytest, requests, ruff']\n"
        "if dependency_check and not Path(os.environ['UV_TEST_MARKER']).exists():\n"
        "    sys.exit(1)\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
    )
    python_wrapper.chmod(0o755)
    env["PYTHON"] = str(python_wrapper)

    result = command(repo, "bash", "bump_version.sh", env=env)

    assert "Instalando dependências de teste" in result.stdout
    uv_args = json.loads(Path(env["UV_TEST_RESULT"]).read_text())
    assert uv_args == [
        "pip",
        "install",
        "--python",
        str(python_wrapper),
        "-r",
        "requirements-test.txt",
    ]


@pytest.mark.parametrize("problem", ["dirty", "tag", "tests", "empty_notes", "version"])
def test_preflight_or_validation_failure_does_not_bump(release_repo, problem):
    repo, _, env = release_repo
    args = []
    if problem == "dirty":
        (repo / "pending.txt").write_text("Uncommitted work")
    elif problem == "tag":
        command(repo, "git", "tag", "v0.1.5", env=env)
    elif problem == "tests":
        (repo / "tests" / "test_smoke.py").write_text(
            "def test_failure():\n    assert False\n"
        )
        command(repo, "git", "commit", "-am", "Failing test", env=env)
    elif problem == "empty_notes":
        (repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Fixed\n"
        )
        command(repo, "git", "commit", "-am", "Empty notes", env=env)
    else:
        args = ["0.1.4"]
    before = command(repo, "git", "rev-parse", "HEAD", env=env).stdout
    result = command(repo, "bash", "bump_version.sh", *args, env=env, check=False)
    assert result.returncode != 0
    assert json.loads((repo / MANIFEST).read_text())["version"] == "0.1.4"
    assert command(repo, "git", "rev-parse", "HEAD", env=env).stdout == before
    assert not Path(env["GH_TEST_RESULT"]).exists()


def test_github_failure_explains_how_to_resume_without_another_bump(release_repo):
    repo, remote, env = release_repo
    env["GH_TEST_FAIL"] = "1"
    result = command(repo, "bash", "bump_version.sh", env=env, check=False)
    assert result.returncode != 0
    assert "gh release view v0.1.5" in result.stderr
    assert "gh release create v0.1.5" in result.stderr
    assert (
        command(remote, "git", "rev-parse", "refs/tags/v0.1.5", env=env).returncode == 0
    )


def test_rejected_push_keeps_remote_unchanged_and_explains_recovery(release_repo):
    repo, remote, env = release_repo
    original = command(remote, "git", "rev-parse", "refs/heads/main", env=env).stdout
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = command(repo, "bash", "bump_version.sh", env=env, check=False)
    assert result.returncode != 0
    assert (
        "git push --atomic origin HEAD:refs/heads/main refs/tags/v0.1.5"
        in result.stderr
    )
    assert (
        command(remote, "git", "rev-parse", "refs/heads/main", env=env).stdout
        == original
    )
    assert (
        command(
            remote,
            "git",
            "show-ref",
            "--verify",
            "refs/tags/v0.1.5",
            env=env,
            check=False,
        ).returncode
        != 0
    )
    assert not Path(env["GH_TEST_RESULT"]).exists()
