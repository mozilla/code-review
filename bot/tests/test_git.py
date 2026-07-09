# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os.path
from unittest.mock import MagicMock

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
    """The git base is used directly: no Lando git2hg lookup, fall back to default."""
    head = mock_mc_git.repo.head.commit.hexsha

    # Base present locally -> returned as-is
    present = MagicMock(base_revision=head)
    assert mock_mc_git.get_base_identifier([present]) == head

    # Base absent -> fall back to the default revision (no git2hg call)
    absent = MagicMock(base_revision="abcdef123456")
    assert mock_mc_git.get_base_identifier([absent]) == mock_mc_git.default_revision


def test_apply_patches(PhabricatorMock, mock_mc_git):
    """Apply a Phabricator stack as Git commits onto the default revision."""
    build = make_build(PhabricatorMock)

    target = os.path.join(mock_mc_git.dir, "test.txt")
    assert not os.path.exists(target)

    mock_mc_git.apply_build(build)

    # The patched file now has the expected content
    assert os.path.exists(target)
    assert open(target).read() == "First Line\nSecond Line\n"

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
