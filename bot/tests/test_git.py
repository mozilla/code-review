# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import base64
import json
import os.path
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import MockBuild
from git.exc import GitCommandError

from code_review_bot.git import GitRepository, GitWorker
from code_review_bot.vcs import MAX_PUSH_RETRIES, BaseWorker

LINT_EXTRA_PARAMS = {
    "optimize_target_tasks": True,
    "target_tasks_method": "codereview",
}

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
    """try_task_config.json is written and committed by the bot author, and
    records the commit the stack was applied on as the push's base revision."""
    base = mock_mc_git.repo.commit(mock_mc_git.default_revision).hexsha
    build = make_build(PhabricatorMock)
    parent = mock_mc_git.apply_build(build)
    assert mock_mc_git.base_commit == base
    assert parent == mock_mc_git.repo.head.commit.hexsha
    commit = mock_mc_git.add_try_commit(build, LINT_EXTRA_PARAMS, parent)
    assert commit == mock_mc_git.repo.head.commit.hexsha

    config_path = os.path.join(mock_mc_git.dir, "try_task_config.json")
    assert os.path.exists(config_path)
    assert json.load(open(config_path)) == {
        "version": 2,
        "parameters": {
            "target_tasks_method": "codereview",
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-deadbeef",
            "base_rev": base,
        },
    }
    # The caller's parameters are left untouched
    assert "base_rev" not in LINT_EXTRA_PARAMS

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
    parent = mock_mc_git.apply_build(build)
    commit = mock_mc_git.add_try_commit(build, LINT_EXTRA_PARAMS, parent)

    pushed = mock_mc_git.push_to_try(commit)

    assert pushed == commit == mock_mc_git.repo.head.commit.hexsha
    assert mock_mc_git.revision_id(pushed) == commit

    # The remote try repo received the configured branch at the pushed commit
    from git import Repo

    remote = Repo(mock_mc_git.try_url)
    assert remote.refs["code-review"].commit.hexsha == pushed


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
    parent = mock_mc_git.apply_build(build)
    mock_mc_git.add_try_commit(build, LINT_EXTRA_PARAMS, parent)

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


def test_branch_is_required(tmpdir):
    """A Git repository holds every branch, so the one the patches apply on
    has to be configured: there is no safe default."""
    config = {
        "name": "no-branch",
        "url": "https://github.com/mozilla/test",
        "try_url": str(tmpdir.mkdir("no-branch-try.git").realpath()),
    }
    with pytest.raises(ValueError, match="needs the branch"):
        GitRepository(config, str(tmpdir.realpath()))
    with pytest.raises(ValueError, match="needs the branch"):
        GitRepository({**config, "default_revision": None}, str(tmpdir.realpath()))


def test_clean_requires_the_branch(tmpdir, mock_mc_git):
    """clean() fails loudly when the branch is not on origin, instead of
    silently keeping the previous build's commits."""
    mock_mc_git.branch = "nope"
    assert mock_mc_git.default_revision == "origin/nope"

    with pytest.raises(Exception, match="Branch nope is not on origin"):
        mock_mc_git.clean()


def serve_partial_clones(repo):
    """Let a local repository serve blob-less partial clones over file://, as
    GitHub does (a plain local path would silently ignore the filter)."""
    with repo.config_writer() as cw:
        cw.set_value("uploadpack", "allowFilter", "true")
        cw.set_value("uploadpack", "allowAnySHA1InWant", "true")
    return f"file://{repo.working_dir if not repo.bare else repo.git_dir}"


def test_clone_starts_on_the_branch(tmpdir):
    """The clone checks out the configured branch, and only that one, without
    the file contents of its history; the default revision follows that
    branch on origin across builds."""
    from conftest import build_git_repository

    # An origin with a second branch, one commit ahead of the default one
    origin = build_git_repository(tmpdir, "origin-repo")
    default_branch = origin.active_branch.name
    origin.git.checkout("-b", "beta")
    with open(os.path.join(origin.working_dir, "beta.txt"), "w") as f:
        f.write("beta only")
    origin.index.add(["beta.txt"])
    beta_tip = origin.index.commit("beta commit").hexsha
    origin.git.checkout(default_branch)

    config = {
        "name": "clone-test",
        "url": serve_partial_clones(origin),
        "try_url": str(tmpdir.mkdir("clone-test-try.git").realpath()),
        "default_revision": "beta",
    }
    git_repo = GitRepository(config, str(tmpdir.realpath()))
    git_repo.clone()

    assert git_repo.repo.active_branch.name == "beta"
    assert git_repo.repo.head.commit.hexsha == beta_tip
    assert git_repo.default_revision == "origin/beta"
    # A single-branch, blob-less partial clone that negotiates its pushes
    assert [ref.name for ref in git_repo.repo.remotes.origin.refs] == ["origin/beta"]
    assert git_repo.repo.git.config("remote.origin.promisor") == "true"
    assert git_repo.repo.git.config("remote.origin.partialclonefilter") == "blob:none"
    assert git_repo.repo.git.config("push.negotiate") == "true"
    assert open(os.path.join(git_repo.dir, "beta.txt")).read() == "beta only"

    # A later build picks up the branch's new tip, not the default branch
    origin.git.checkout("beta")
    with open(os.path.join(origin.working_dir, "beta.txt"), "w") as f:
        f.write("beta update")
    origin.index.add(["beta.txt"])
    new_tip = origin.index.commit("beta update").hexsha
    git_repo.clean()
    assert git_repo.repo.head.commit.hexsha == new_tip
    assert git_repo.repo.commit(git_repo.default_revision).hexsha == new_tip


def test_clean_picks_up_remote_updates(tmpdir, mock_mc_git):
    """clean() resets onto the remote-tracking base, so upstream commits
    landed since the last build are picked up (mirrors hg pull)."""
    from git import Actor, Repo

    # Land a commit on origin through another clone, as upstream would
    upstream_dir = str(tmpdir.mkdir("upstream").realpath())
    upstream = Repo.clone_from(mock_mc_git.url, upstream_dir)
    with upstream.config_writer() as cw:
        cw.set_value("user", "name", "test")
        cw.set_value("user", "email", "test")
        cw.set_value("commit", "gpgsign", "false")
    with open(os.path.join(upstream_dir, "update.txt"), "w") as f:
        f.write("upstream update")
    upstream.index.add(["update.txt"])
    actor = Actor("test", "test")
    upstream_tip = upstream.index.commit(
        "upstream update", author=actor, committer=actor
    )
    upstream.remotes.origin.push(mock_mc_git.branch)

    # The local clone still sees the previous tip until cleanup fetches
    assert mock_mc_git.repo.commit(mock_mc_git.default_revision) != upstream_tip
    mock_mc_git.clean()

    assert mock_mc_git.repo.head.commit.hexsha == upstream_tip.hexsha
    assert os.path.exists(os.path.join(mock_mc_git.dir, "update.txt"))
    # Origin is untouched by cleanup
    assert Repo(mock_mc_git.url).commit(mock_mc_git.branch) == upstream_tip


def test_worker_failure_git(PhabricatorMock, mock_mc_git):
    """A non-retryable Git error yields a fail:git result with the error log."""
    build = make_build(PhabricatorMock)
    error = GitCommandError("git apply", 128, b"fatal: corrupt patch at line 3")
    mock_mc_git.apply_build = MagicMock(side_effect=error)

    worker = GitWorker()
    mode, out_build, details = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

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
        "default_revision": "main",
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

    # The token is sent as a basic authorization header for the url's host,
    # configured through git's environment instead of the url itself
    credentials = base64.b64encode(b"x-access-token:generated-token").decode()
    assert git_repo.push_environment(
        "https://github.com/mozilla-releng/staging-firefox.git"
    ) == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {credentials}",
    }


def test_push_environment_local_paths(mock_mc_git):
    """Local paths (as used by the test remotes) are never authenticated."""
    assert mock_mc_git.push_environment(mock_mc_git.try_url) == {}


def test_push_to_try_keeps_token_off_the_command_line(
    PhabricatorMock, mock_mc_git, monkeypatch
):
    """The push command only carries the plain url: the token is scoped to
    the push through git's environment and stays out of the error messages
    GitPython builds from the command line."""
    from git.cmd import Git

    build = make_build(PhabricatorMock)
    try_url = "https://github.com/mozilla/test-try.git"
    mock_mc_git.try_url = try_url
    mock_mc_git.github_token = MagicMock(return_value="secret-token")

    pushes = []
    real_execute = Git.execute

    def fake_execute(self, command, *args, **kwargs):
        if "push" not in command:
            return real_execute(self, command, *args, **kwargs)
        pushes.append((command, dict(self.environment())))
        raise GitCommandError(command, 128, b"fatal: denied")

    monkeypatch.setattr(Git, "execute", fake_execute)

    worker = GitWorker()
    mode, _, details = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

    assert mode == "fail:git"
    assert "secret-token" not in details["message"]
    assert len(pushes) == 1
    command, environment = pushes[0]
    tip = mock_mc_git.repo.head.commit.hexsha
    assert command[:2] == ["git", "push"]
    assert try_url in command and f"{tip}:refs/heads/code-review" in command
    assert all("secret-token" not in arg for arg in command)
    assert environment == mock_mc_git.push_environment(try_url)
    # The push environment is dropped once the push is over
    assert mock_mc_git.repo.git.environment() == {}


def test_worker_run_success(PhabricatorMock, mock_mc_git):
    """Full success path: apply, configure try, push, return treeherder link."""
    build = make_build(PhabricatorMock)

    worker = GitWorker()
    result = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

    tip = mock_mc_git.repo.head.commit
    assert result == (
        "success",
        build,
        {
            "revision": tip.hexsha,
            "treeherder_url": (
                "https://treeherder.mozilla.org/#/jobs?repo=staging-firefox&revision="
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
    mode, out_build, details = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

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
    mode, out_build, details = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

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
    monkeypatch.setattr("code_review_bot.vcs.time.sleep", lambda *a, **k: None)

    worker = GitWorker()

    # The Git worker keeps the default no-op hook: no treestatus gate
    assert GitWorker.wait_try_available is BaseWorker.wait_try_available

    mode, out_build, details = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)

    assert mode == "fail:git"
    # Initial attempt + one per retry
    assert mock_mc_git.push_to_try.call_count == MAX_PUSH_RETRIES + 1


def test_head_branch_template(tmpdir, PhabricatorMock, mock_mc_git):
    """The default head_branch is rendered per build, custom templates too."""
    build = make_build(PhabricatorMock)

    # Default configuration builds a unique branch per diff
    config = {
        "name": "mozilla-central",
        "url": "https://github.com/mozilla/test",
        "try_url": "https://github.com/mozilla/test-try",
        "try_name": "try",
        "default_revision": "main",
    }
    repo = GitRepository(config, str(tmpdir.realpath()))
    assert repo.head_branch == "code-review/D{revision_id}-{diff_id}"
    assert repo.render_push_branch(build) == "code-review/D5678-1234"

    # An unset repository head_branch reaches the config as None and still
    # falls back to the default template
    repo = GitRepository({**config, "head_branch": None}, str(tmpdir.realpath()))
    assert repo.head_branch == "code-review/D{revision_id}-{diff_id}"

    # Environments pick their own pattern, e.g. the dev prefix
    repo = GitRepository(
        {**config, "head_branch": "dev/code-review/D{revision_id}"},
        str(tmpdir.realpath()),
    )
    assert repo.render_push_branch(build) == "dev/code-review/D5678"

    # Static branch names are rendered unchanged
    assert mock_mc_git.render_push_branch(build) == "code-review"

    # Custom templates may combine identifiers
    mock_mc_git.head_branch = "cr/{revision_id}-{diff_id}"
    assert mock_mc_git.render_push_branch(build) == "cr/5678-1234"

    # Unknown placeholders are rejected
    mock_mc_git.head_branch = "cr/{unknown}"
    with pytest.raises(Exception, match="Invalid head_branch template"):
        mock_mc_git.render_push_branch(build)


def test_git_clone_fetches_the_pushed_commit_by_sha(tmpdir, monkeypatch):
    """Publication clones the pushed commit by SHA and checks it out: a later
    force push moving the branch (the other analysis mode of the same diff, a
    re-fired build) must not hide it, as a Mercurial try head stays
    addressable by hash."""
    from conftest import build_git_repository
    from git import Repo

    from code_review_bot.git import git_clone

    # Local paths stand in for the github urls
    monkeypatch.setattr(
        "code_review_bot.git.build_repo_slug",
        lambda url: os.path.basename(url.rstrip("/")).removesuffix(".git"),
    )

    origin = build_git_repository(tmpdir, "origin-repo")
    try_dir, push = make_try_repository(tmpdir, origin)
    lint = push("lint")
    build = push("build")
    # The second push moved the branch: the first commit is unreachable
    assert Repo(try_dir).refs["code-review/D1-2"].commit.hexsha == build
    assert Repo(try_dir).git.branch("--contains", lint) == ""

    cache = tmpdir.mkdir("git-cache")
    repo = git_clone(origin.working_dir, try_dir, lint, Path(str(cache)))

    assert repo.working_dir == str(cache.join("origin-repo"))
    assert repo.head.is_detached
    assert repo.head.commit.hexsha == lint
    # The working tree holds that commit's files, nothing else
    assert open(os.path.join(repo.working_dir, "lint.txt")).read() == "lint"
    assert not os.path.exists(os.path.join(repo.working_dir, "build.txt"))
    assert repo.git.status("--short") == ""

    # A reused clone is moved to another pushed commit the same way
    repo = git_clone(origin.working_dir, try_dir, build, Path(str(cache)))
    assert repo.head.commit.hexsha == build
    assert open(os.path.join(repo.working_dir, "build.txt")).read() == "build"
    assert not os.path.exists(os.path.join(repo.working_dir, "lint.txt"))


def make_try_repository(tmpdir, origin):
    """A bare "try" repository serving any commit by SHA and partial fetches,
    as GitHub does, and a push() helper committing a file on top of origin's
    tip in another clone and force pushing it to the branch code-review/D1-2,
    so the commit only exists on the try repository."""
    from git import Actor, Repo

    base = origin.head.commit.hexsha
    actor = Actor("test", "test")
    try_dir = str(tmpdir.mkdir("try.git").realpath())
    try_repo = Repo.init(try_dir, bare=True)
    with try_repo.config_writer() as cw:
        cw.set_value("uploadpack", "allowAnySHA1InWant", "true")
        cw.set_value("uploadpack", "allowFilter", "true")

    pusher = Repo.clone_from(origin.working_dir, str(tmpdir.mkdir("pusher")))
    with pusher.config_writer() as cw:
        cw.set_value("user", "name", "test")
        cw.set_value("user", "email", "test")
        cw.set_value("commit", "gpgsign", "false")

    def push(name, files=None):
        for path, content in (files or {f"{name}.txt": name}).items():
            full = os.path.join(pusher.working_dir, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
            pusher.index.add([path])
        commit = pusher.index.commit(name, author=actor, committer=actor).hexsha
        pusher.git.push(try_dir, f"{commit}:refs/heads/code-review/D1-2", force=True)
        pusher.git.reset("--hard", base)
        return commit

    return try_dir, push


def test_git_clone_checks_out_only_the_issue_files(tmpdir, monkeypatch):
    """With the issue paths, publication fetches the pushed commit without its
    history nor blobs and checks out only those files, as `cat_files` extracts
    them for Mercurial: the repository is never cloned in full."""
    from conftest import build_git_repository

    from code_review_bot.git import git_clone

    monkeypatch.setattr(
        "code_review_bot.git.build_repo_slug",
        lambda url: os.path.basename(url.rstrip("/")).removesuffix(".git"),
    )

    origin = build_git_repository(tmpdir, "origin-repo")
    try_dir, push = make_try_repository(tmpdir, origin)
    first = push(
        "first", {"dom/first.cpp": "int first;", "js/src/other.cpp": "int other;"}
    )
    second = push("second", {"dom/second.cpp": "int second;"})

    cache = tmpdir.mkdir("git-cache")
    repo = git_clone(
        origin.working_dir,
        try_dir,
        first,
        Path(str(cache)),
        # Issue paths may be missing from the commit, or not even be files
        paths=["dom/first.cpp", "missing.cpp", "js/src", "/etc/passwd", "../x"],
    )

    assert repo.working_dir == str(cache.join("origin-repo"))
    assert repo.head.is_detached
    assert repo.head.commit.hexsha == first
    work = Path(repo.working_dir)
    assert (work / "dom/first.cpp").read_text() == "int first;"
    # Only the requested files exist locally, not the rest of the tree
    assert not (work / "js/src/other.cpp").exists()
    assert not (work / "README.md").exists()
    assert not (work / "missing.cpp").exists()
    # No history and no other blobs were fetched
    assert repo.git.rev_list("--count", first) == "1"
    assert repo.git.config("remote.try.promisor") == "true"
    # Nothing was cloned or fetched from the base repository
    assert repo.git.rev_list("--all", "--count") == "1"

    # A reused repository drops the previous files before the new revision,
    # so a file removed upstream does not pass the existence checks
    repo = git_clone(
        origin.working_dir, try_dir, second, Path(str(cache)), paths=["dom/second.cpp"]
    )
    assert repo.head.commit.hexsha == second
    assert (work / "dom/second.cpp").read_text() == "int second;"
    assert not (work / "dom/first.cpp").exists()

    # Without paths, the whole tree is checked out as before
    repo = git_clone(origin.working_dir, try_dir, first, Path(str(cache)))
    assert (work / "dom/first.cpp").exists()
    assert (work / "js/src/other.cpp").exists()
    assert (work / "README.md").exists()


def test_worker_pushes_from_a_partial_clone(tmpdir, PhabricatorMock):
    """The whole analysis runs on a blob-less clone: the files of the base
    revision are fetched when it is checked out, the patches apply on them
    and the push carries the new commits; what the try repository lacks on
    top of that is fetched from origin on the way."""
    from conftest import build_git_repository
    from git import Actor, Repo

    origin = build_git_repository(tmpdir, "origin-repo")
    branch = origin.active_branch.name
    actor = Actor("test", "test")
    # A second version of the Readme: the clone never fetches the first one
    with open(os.path.join(origin.working_dir, "README.md"), "w") as f:
        f.write("Hello World v2")
    origin.index.add(["README.md"])
    tip = origin.index.commit("Readme v2", author=actor, committer=actor).hexsha

    try_dir = str(tmpdir.mkdir("partial-try.git").realpath())
    Repo.init(try_dir, bare=True)
    config = {
        "name": "partial",
        "url": serve_partial_clones(origin),
        "try_url": try_dir,
        "try_name": "staging-firefox",
        "default_revision": branch,
        "head_branch": "code-review/D{revision_id}-{diff_id}",
    }
    git_repo = GitRepository(config, str(tmpdir.realpath()))
    git_repo.clone()
    assert git_repo.repo.head.commit.hexsha == tip
    missing = [
        line
        for line in git_repo.repo.git.rev_list(
            "--objects", "--missing=print", "--all"
        ).splitlines()
        if line.startswith("?")
    ]
    assert len(missing) == 1, "the first Readme blob should be a promised object"

    build = make_build(PhabricatorMock)
    mode, out_build, details = GitWorker().run(git_repo, build, LINT_EXTRA_PARAMS)
    assert mode == "success", details
    assert out_build is build

    pushed = Repo(try_dir).refs["code-review/D5678-1234"].commit
    assert pushed.hexsha == details["revision"] == git_repo.repo.head.commit.hexsha
    assert (pushed.tree / "README.md").data_stream.read() == b"Hello World v2"
    assert (pushed.tree / "test.txt").data_stream.read() == b"First Line\nSecond Line\n"
    assert (
        json.load((pushed.tree / "try_task_config.json").data_stream)["parameters"][
            "base_rev"
        ]
        == tip
    )
    # The push went through on the partial clone, which stays one
    assert git_repo.repo.git.config("remote.origin.promisor") == "true"


def test_worker_pushes_templated_branch(PhabricatorMock, mock_mc_git):
    """The rendered per-build branch is what lands on the try remote."""
    from git import Repo

    mock_mc_git.head_branch = "code-review/D{revision_id}"
    build = make_build(PhabricatorMock)

    worker = GitWorker()
    mode, _, _ = worker.run(mock_mc_git, build, LINT_EXTRA_PARAMS)
    assert mode == "success"

    tip = mock_mc_git.repo.head.commit
    remote = Repo(mock_mc_git.try_url)
    assert remote.refs["code-review/D5678"].commit.hexsha == tip.hexsha
