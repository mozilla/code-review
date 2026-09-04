# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from unittest.mock import MagicMock

import pytest

from code_review_bot.config import settings
from code_review_bot.revisions import GithubRevision, Revision
from code_review_bot.revisions.phabricator import PhabricatorRevision

GIT_ENV = {
    "GECKO_REPOSITORY_TYPE": "git",
    "GECKO_BASE_REPOSITORY": "https://github.com/mozilla-releng/staging-firefox",
    "GECKO_HEAD_REPOSITORY": "https://github.com/mozilla-releng/staging-firefox",
    "GECKO_BASE_REV": "a" * 40,
    "GECKO_HEAD_REV": "b" * 40,
}


def test_from_try_task_git_pull_request(monkeypatch):
    """A git revision with a pull request number is a Github revision."""
    monkeypatch.setattr(GithubRevision, "load_patch", lambda self: "patch")
    decision_task = {
        "payload": {"env": {**GIT_ENV, "GECKO_PULL_REQUEST_NUMBER": "123"}}
    }

    revision = Revision.from_try_task({"extra": {}}, decision_task, None)

    assert isinstance(revision, GithubRevision)
    assert revision.repository_type == "git"
    assert revision.pull_number == 123


def test_from_try_task_git_push(monkeypatch):
    """A git push without a pull request is handled as a Phabricator revision."""
    calls = []
    monkeypatch.setattr(
        PhabricatorRevision,
        "from_try_task",
        lambda code_review, decision_task, phabricator: calls.append(code_review)
        or "phab-revision",
    )
    decision_task = {"payload": {"env": dict(GIT_ENV)}}
    try_task = {"extra": {"code-review": {"phabricator-diff": "PHID-HMBT-x"}}}

    assert Revision.from_try_task(try_task, decision_task, None) == "phab-revision"
    assert calls == [{"phabricator-diff": "PHID-HMBT-x"}]


def test_phabricator_revision_repository_type(mock_config):
    """Phabricator revisions expose their repository type and git slug."""
    git_revision = PhabricatorRevision(
        base_repository="https://github.com/mozilla-releng/staging-firefox",
        repository_type="git",
    )
    assert git_revision.repository_type == "git"
    assert git_revision.repository_slug == "mozilla-releng_staging-firefox"

    hg_revision = PhabricatorRevision(
        base_repository="https://hg.mozilla.org/mozilla-unified"
    )
    assert hg_revision.repository_type == "hg"
    with pytest.raises(AssertionError):
        hg_revision.repository_slug


def test_clone_repository_follows_repository_type(mock_workflow, monkeypatch, tmp_path):
    """Publication cloning follows the repository type, not the revision class."""
    git_clone = MagicMock()
    robust_checkout = MagicMock()
    monkeypatch.setattr("code_review_bot.workflow.git_clone", git_clone)
    monkeypatch.setattr("code_review_bot.workflow.robust_checkout", robust_checkout)
    monkeypatch.setattr(settings, "git_cache", tmp_path)
    monkeypatch.setattr(settings, "mercurial_cache", tmp_path)

    revision = MagicMock(
        repository_type="git",
        base_repository="https://github.com/mozilla-releng/staging-firefox",
        head_repository="https://github.com/mozilla-releng/staging-firefox",
        head_changeset="b" * 40,
    )
    mock_workflow.clone_available = False
    mock_workflow.clone_repository(revision)
    assert git_clone.call_count == 1
    assert robust_checkout.call_count == 0
    assert git_clone.call_args.kwargs == {
        "base_repository": "https://github.com/mozilla-releng/staging-firefox",
        "head_repository": "https://github.com/mozilla-releng/staging-firefox",
        "revision": "b" * 40,
        "destination": tmp_path,
    }

    revision.repository_type = "hg"
    mock_workflow.clone_available = False
    mock_workflow.clone_repository(revision)
    assert git_clone.call_count == 1
    assert robust_checkout.call_count == 1
