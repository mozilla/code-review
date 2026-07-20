# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os.path
from unittest.mock import MagicMock

import pytest
from conftest import MockBuild
from git.exc import GitCommandError

from code_review_bot.git import MAX_PUSH_RETRIES, GitRepository, GitWorker

# A diff whose base revision exists neither in Git nor Mercurial: patches will be
# applied on the repository's default revision (mirrors the Mercurial tests).
DIFF = {
    "phid": "PHID-DIFF-test123",
    "revisionPHID": "PHID-DREV-deadbeef",
    "id": 1234,
    "baseRevision": "abcdef123456",
}


def make_build(phabricator_mock):
    """Build a MockBuild with its patch stack loaded from the Phabricator mock."""
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", dict(DIFF))
    with phabricator_mock as phab:
        phab.load_patches_stack(build)
    return build


def test_normalize_patch():
    """Trailing Mercurial-style timestamps are stripped from ---/+++ headers."""
    patch = (
        "diff -r 000000000000 test.txt\n"
        "--- /dev/null Thu Jan 01 00:00:00 1970 +0000\n"
        "+++ b/test.txt  Tue Feb 05 17:23:40 2019 +0100\n"
        "@@ -0,0 +1,1 @@\n"
        "+First Line\n"
    )
    normalized = GitRepository.normalize_patch(patch)
    assert "--- /dev/null\n" in normalized
    assert "+++ b/test.txt\n" in normalized
    assert "1970" not in normalized and "2019" not in normalized

    # Git-style headers (no timestamp) are left untouched
    git_patch = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
    assert GitRepository.normalize_patch(git_patch) == git_patch


def test_has_revision(mock_mc_git):
    head = mock_mc_git.repo.head.commit.hexsha
    assert mock_mc_git.has_revision(head) is True
    assert mock_mc_git.has_revision(head[:12]) is True
    assert mock_mc_git.has_revision("deadbeef" * 5) is False
    assert mock_mc_git.has_revision("") is False
    assert mock_mc_git.has_revision(None) is False


def test_get_base_identifier_no_git2hg(mock_mc_git):
    """The git base is used directly: no Lando git2hg lookup."""
    head = mock_mc_git.repo.head.commit.hexsha

    present = MagicMock(base_revision=head)
    assert mock_mc_git.get_base_identifier([present]) == head

    # An unknown base is returned as-is: apply_build detects it is missing,
    # records it on the build and falls back to the default revision
    absent = MagicMock(base_revision="abcdef123456")
    assert mock_mc_git.get_base_identifier([absent]) == "abcdef123456"


def test_apply_patches(PhabricatorMock, mock_mc_git):
    """Apply a Phabricator stack as Git commits onto the default revision."""
    build = make_build(PhabricatorMock)

    target = os.path.join(mock_mc_git.dir, "test.txt")
    assert not os.path.exists(target)

    mock_mc_git.apply_build(build)

    # The patched file now has the expected content
    assert os.path.exists(target)
    assert open(target).read() == "First Line\nSecond Line\n"

    # The unknown base revision is recorded on the build with the fallback used
    assert build.missing_base_revision is True
    assert build.base_revision == build.stack[0].base_revision
    assert build.actual_base_revision == mock_mc_git.default_revision

    # Commits (newest first): the two patches on top of the base Readme
    commits = list(mock_mc_git.repo.iter_commits())
    assert [c.message.strip() for c in commits] == [
        "Bug XXX - A second commit message\nDifferential Diff: PHID-DIFF-test123",
        "Bug XXX - A first commit message\nDifferential Diff: PHID-DIFF-xxxx",
        "Readme",
    ]
    assert [f"{c.author.name} <{c.author.email}>" for c in commits] == [
        "John Doe <john@allizom.org>",
        "randomUsername <random>",
        "test <test>",
    ]


def test_add_try_commit(PhabricatorMock, mock_mc_git):
    """try_task_config.json is written and committed by the bot author."""
    build = make_build(PhabricatorMock)
    mock_mc_git.apply_build(build)
    mock_mc_git.add_try_commit(build)

    config_path = os.path.join(mock_mc_git.dir, "try_task_config.json")
    assert os.path.exists(config_path)
    assert json.load(open(config_path)) == {
        "version": 2,
        "parameters": {
            "target_tasks_method": "codereview",
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-deadbeef",
        },
    }

    head = next(mock_mc_git.repo.iter_commits())
    assert (
        head.message.strip()
        == "try_task_config for code-review\nDifferential Diff: PHID-DIFF-test123"
    )
    assert (
        f"{head.author.name} <{head.author.email}>"
        == "code review bot <release-mgmt-analysis@mozilla.com>"
    )


def test_push_to_try(PhabricatorMock, mock_mc_git):
    """push_to_try pushes the prepared HEAD to the configured branch/remote."""
    build = make_build(PhabricatorMock)
    mock_mc_git.apply_build(build)
    mock_mc_git.add_try_commit(build)

    pushed = mock_mc_git.push_to_try()

    assert pushed == mock_mc_git.repo.head.commit

    # The remote try repo received the configured branch at the pushed commit
    from git import Repo

    remote = Repo(mock_mc_git.try_url)
    assert remote.refs["code-review"].commit.hexsha == pushed.hexsha


def test_clean(mock_mc_git):
    """clean() resets tracked changes and removes untracked files."""
    untracked = os.path.join(mock_mc_git.dir, "untracked.txt")
    with open(untracked, "w") as f:
        f.write("dirty")
    readme = os.path.join(mock_mc_git.dir, "README.md")
    with open(readme, "w") as f:
        f.write("changed")
    assert mock_mc_git.repo.is_dirty(untracked_files=True)

    mock_mc_git.clean()

    assert not mock_mc_git.repo.is_dirty(untracked_files=True)
    assert not os.path.exists(untracked)
    assert open(readme).read() == "Hello World"


def test_clean_drops_previous_build(PhabricatorMock, mock_mc_git):
    """A reused clone does not accumulate a previous build's commits."""
    branch = mock_mc_git.default_revision
    base = mock_mc_git.repo.commit(branch).hexsha
    assert mock_mc_git.repo.git.rev_list("--count", branch).strip() == "1"

    # First build: apply the stack and the try_task_config commit
    build = make_build(PhabricatorMock)
    mock_mc_git.apply_build(build)
    mock_mc_git.add_try_commit(build)

    # Those commits live on a detached HEAD; the branch has not moved
    assert mock_mc_git.repo.head.is_detached
    assert mock_mc_git.repo.commit(branch).hexsha == base
    assert os.path.exists(os.path.join(mock_mc_git.dir, "test.txt"))

    # Cleaning returns to the pristine base, dropping the build's commits
    mock_mc_git.clean()

    assert mock_mc_git.repo.head.commit.hexsha == base
    assert mock_mc_git.repo.git.rev_list("--count", branch).strip() == "1"
    assert not os.path.exists(os.path.join(mock_mc_git.dir, "test.txt"))
    assert not os.path.exists(os.path.join(mock_mc_git.dir, "try_task_config.json"))


def test_clean_requires_pristine_base(tmpdir):
    """Without a configured default_revision nor an origin remote, clean()
    fails loudly instead of silently keeping the previous build's commits."""
    from conftest import build_git_repository

    repo = build_git_repository(tmpdir, "no-default")
    config = {
        "name": "no-default",
        "url": "https://github.com/mozilla/test",
        "try_url": str(tmpdir.mkdir("no-default-try.git").realpath()),
    }
    git_repo = GitRepository(config, str(tmpdir.realpath()))
    git_repo._repo = repo

    with pytest.raises(Exception, match="configure default_revision"):
        git_repo.clean()


def test_clean_picks_up_remote_updates(tmpdir, mock_mc_git):
    """clean() resets onto the remote-tracking base, so upstream commits
    landed since the last build are picked up (mirrors hg pull)."""
    from git import Actor, Repo

    # Clone the repo to act as its origin, and move it one commit ahead
    origin_dir = str(tmpdir.mkdir("origin-repo").realpath())
    origin = mock_mc_git.repo.clone(origin_dir)
    with origin.config_writer() as cw:
        cw.set_value("user", "name", "test")
        cw.set_value("user", "email", "test")
        cw.set_value("commit", "gpgsign", "false")
    with open(os.path.join(origin_dir, "update.txt"), "w") as f:
        f.write("upstream update")
    origin.index.add(["update.txt"])
    actor = Actor("test", "test")
    upstream_tip = origin.index.commit("upstream update", author=actor, committer=actor)

    mock_mc_git.repo.create_remote("origin", origin_dir)
    mock_mc_git.clean()

    assert mock_mc_git.repo.head.commit.hexsha == upstream_tip.hexsha
    assert os.path.exists(os.path.join(mock_mc_git.dir, "update.txt"))
    # The remote in the local clone is untouched by cleanup
    assert Repo(origin_dir).head.commit.hexsha == upstream_tip.hexsha


def test_worker_failure_git(PhabricatorMock, mock_mc_git):
    """A non-retryable Git error yields a fail:git result with the error log."""
    build = make_build(PhabricatorMock)
    error = GitCommandError("git apply", 128, b"fatal: corrupt patch at line 3")
    mock_mc_git.apply_build = MagicMock(side_effect=error)

    worker = GitWorker()
    mode, out_build, details = worker.run(mock_mc_git, build)

    assert mode == "fail:git"
    assert out_build is build
    assert "corrupt patch" in details["message"]


def test_github_token(monkeypatch, tmpdir):
    """An installation token is generated from the App credentials, restricted
    to the try repository, and cached for the run."""
    from conftest import build_git_repository

    repo = build_git_repository(tmpdir, "app-repo")
    config = {
        "name": "app-repo",
        "url": "https://github.com/mozilla-releng/staging-firefox",
        "try_url": "https://github.com/mozilla-releng/staging-firefox.git",
        "github_app_id": 12345,
        "github_app_privkey": "AppPrivateKey",
    }
    git_repo = GitRepository(config, str(tmpdir.realpath()))
    git_repo._repo = repo

    calls = []

    class FakeInstallationAuth:
        def __init__(self, app_auth, owner, repositories):
            calls.append((app_auth, owner, repositories))

        async def get_token(self):
            return "generated-token"

        async def close(self):
            pass

    monkeypatch.setattr(
        "code_review_bot.git.AppAuth", lambda app_id, privkey: (app_id, privkey)
    )
    monkeypatch.setattr("code_review_bot.git.AppInstallationAuth", FakeInstallationAuth)

    assert git_repo.github_token() == "generated-token"
    assert calls == [((12345, "AppPrivateKey"), "mozilla-releng", ["staging-firefox"])]

    # Cached: no second generation
    assert git_repo.github_token() == "generated-token"
    assert len(calls) == 1

    # The token is injected in https urls only
    assert (
        git_repo.authenticated_url(
            "https://github.com/mozilla-releng/staging-firefox.git"
        )
        == "https://git:generated-token@github.com/mozilla-releng/staging-firefox.git"
    )


def test_authenticated_url_local_paths(mock_mc_git):
    """Local paths (as used by the test remotes) are never authenticated."""
    assert mock_mc_git.authenticated_url(mock_mc_git.try_url) == mock_mc_git.try_url


def test_worker_run_success(PhabricatorMock, mock_mc_git):
    """Full success path: apply, configure try, push, return treeherder link."""
    build = make_build(PhabricatorMock)

    worker = GitWorker()
    result = worker.run(mock_mc_git, build)

    tip = mock_mc_git.repo.head.commit
    assert result == (
        "success",
        build,
        {
            "revision": tip.hexsha,
            "treeherder_url": (
                "https://treeherder.mozilla.org/#/jobs?repo=try&revision="
                f"{tip.hexsha}"
            ),
        },
    )

    # The remote try repo received the configured branch at the pushed commit
    from git import Repo

    remote = Repo(mock_mc_git.try_url)
    assert remote.refs["code-review"].commit.hexsha == tip.hexsha


def test_worker_skippable(PhabricatorMock, mock_mc_git):
    """A patch touching only skippable files is not pushed to try."""
    build = make_build(PhabricatorMock)

    worker = GitWorker(skippable_files=["test.txt"])
    mode, out_build, details = worker.run(mock_mc_git, build)

    assert mode == "fail:ineligible"
    assert out_build is build
    assert "skippable" in details["message"]
    # Nothing was pushed
    from git import Repo

    assert "code-review" not in Repo(mock_mc_git.try_url).refs


def test_worker_failure_general(PhabricatorMock, mock_mc_git):
    """A non-Git error while applying yields a fail:general result."""
    build = make_build(PhabricatorMock)
    mock_mc_git.apply_build = MagicMock(side_effect=Exception("boom"))

    worker = GitWorker()
    mode, out_build, details = worker.run(mock_mc_git, build)

    assert mode == "fail:general"
    assert details["message"] == "boom"


def test_worker_retry_no_treestatus(PhabricatorMock, mock_mc_git, monkeypatch):
    """Eligible push errors are retried (no treestatus wait) up to the max."""
    build = make_build(PhabricatorMock)

    # Isolate the worker's retry logic from the repo mechanics
    mock_mc_git.clean = MagicMock()
    mock_mc_git.apply_build = MagicMock()
    mock_mc_git.add_try_commit = MagicMock()
    error = GitCommandError(
        "git push", 128, b"fatal: Could not read from remote repository"
    )
    mock_mc_git.push_to_try = MagicMock(side_effect=error)

    # Don't actually wait through the exponential backoff
    monkeypatch.setattr("code_review_bot.git.time.sleep", lambda *a, **k: None)

    worker = GitWorker()

    # The Git worker has no treestatus gate at all
    assert not hasattr(worker, "wait_try_available")

    mode, out_build, details = worker.run(mock_mc_git, build)

    assert mode == "fail:git"
    # Initial attempt + one per retry
    assert mock_mc_git.push_to_try.call_count == MAX_PUSH_RETRIES + 1
