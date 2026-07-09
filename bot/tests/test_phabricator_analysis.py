# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import tempfile
from unittest import mock
from unittest.mock import MagicMock

import pytest
from libmozdata.phabricator import BuildState, ConduitError

from code_review_bot import mercurial
from code_review_bot import workflow as workflow_module
from code_review_bot.analysis import (
    LANDO_FAILURE_HG_MESSAGE,
    PhabricatorRevisionBuild,
    publish_analysis_lando,
    publish_analysis_phabricator,
)
from code_review_bot.config import RepositoryConf
from code_review_bot.revisions import PhabricatorRevision
from code_review_bot.sources.phabricator import PhabricatorActions


def test_revision(mock_phabricator):
    """
    Validate the creation of a Revision in analysis context
    using Phabricator webhook payload
    """

    with mock_phabricator as api:
        revision = PhabricatorRevision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
        )

    assert revision.as_dict() == {
        "base_changeset": "default",
        "base_repository": "https://hg.mozilla.org/mozilla-central",
        "bugzilla_id": 1234567,
        "diff_id": 42,
        "diff_phid": "PHID-DIFF-testABcd12",
        "has_clang_files": False,
        "head_changeset": None,
        "head_repository": None,
        "id": 51,
        "mercurial_revision": None,
        "phid": "PHID-DREV-zzzzz",
        "repository": None,
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "url": "https://phabricator.test/D51",
    }
    assert revision.build_target_phid == "PHID-HMBT-test"
    assert revision.phabricator_phid == "PHID-DREV-zzzzz"
    assert revision.base_repository_conf == RepositoryConf(
        name="mozilla-central",
        try_name="try",
        url="https://hg.mozilla.org/mozilla-central",
        try_url="ssh://hg.mozilla.org/try",
        decision_env_prefix="GECKO",
        ssh_user="reviewbot@mozilla.com",
    )
    assert revision.repository_try_name == "try"


def test_workflow(
    mock_mercurial_repo,
    mock_phabricator,
    mock_workflow,
    mock_config,
    tmpdir,
    monkeypatch,
):
    """
    Validate the creation of a Revision in analysis context
    using Phabricator webhook payload
    """

    # Enable clone & push in settings
    mock_config.mercurial_cache = tmpdir
    mock_config.ssh_key = "Dummy Private SSH Key"

    # Capture hg calls
    hgrun_calls = []

    def mock_hgrun(cmd):
        hgrun_calls.append(cmd)

    monkeypatch.setattr(mercurial, "hg_run", mock_hgrun)

    # Build never expires otherwise the analysis stops early
    monkeypatch.setattr(PhabricatorActions, "is_expired_build", lambda _, build: False)

    # Control ssh key destination
    ssh_key_path = tmpdir / "ssh.key"
    monkeypatch.setattr(tempfile, "mkstemp", lambda suffix: (None, ssh_key_path))

    # Create repo dir to write try task config
    repo_path = tmpdir / "mozilla-central"
    repo_path.mkdir()

    # Run the analysis on fake revision
    with mock_phabricator as api:
        mock_workflow.phabricator = api

        revision = PhabricatorRevision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
        )

        mock_workflow.start_analysis(revision)

    # Check hgrun initial call to clone mozilla central through robust checkout
    assert hgrun_calls == [
        [
            "robustcheckout",
            b"--purge",
            f"--sharebase={tmpdir}/mozilla-central-shared".encode(),
            b"--branch=default",
            b"--",
            "https://hg.mozilla.org/mozilla-central",
            repo_path,
        ]
    ]

    # Check try task config has been written with code-review trigger
    try_task = tmpdir / "mozilla-central" / "try_task_config.json"
    assert try_task.exists()
    assert json.load(try_task.open()) == {
        "parameters": {
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-test",
            "target_tasks_method": "codereview",
        },
        "version": 2,
    }

    # Check all calls made to mercurial repo
    assert mock_mercurial_repo._calls == [
        # Cleanup
        "cbout",
        "cberr",
        (
            "revert",
            str(repo_path).encode(),
            {
                "all": True,
            },
        ),
        (
            "rawcommand",
            [
                b"strip",
                b"--rev=roots(outgoing())",
                b"--force",
            ],
        ),
        # Pull
        "pull",
        (
            "identify",
            "coffeedeadbeef123456789",
        ),
        (
            "identify",
            "coffeedeadbeef123456789",
        ),
        (
            "identify",
            "coffeedeadbeef123456789",
        ),
        # Checkout revision
        (
            "update",
            {
                "clean": True,
                "rev": "coffeedeadbeef123456789",
            },
        ),
        (
            "status",
            {
                "added": True,
                "deleted": True,
                "modified": True,
                "removed": True,
            },
        ),
        # Apply patch
        (
            "import",
            b"diff --git a/test.txt b/test.txt\nindex 557db03..5eb0bec 100644\n-"
            b"-- a/test.txt\n+++ b/test.txt\n@@ -1 +1,2 @@\n Hello World\n+Second "
            b"line\ndiff --git a/test.cpp b/test.cpp\nnew file mode 100644\nindex"
            b" 000000..5eb0bec 100644\n--- a/test.cpp\n+++ b/test.cpp\n@@ -1 +1,2"
            b" @@\n+Hello World\n",
            {
                "message": b"Random commit message\nDifferential Diff: PHID-DIFF-testABcd12",
                "similarity": 95,
                "user": b"test <test@mozilla.com>",
            },
        ),
        # Add try_task_config
        (
            "add",
            str(try_task).encode(),
        ),
        # Commit try_task_config
        (
            "commit",
            {
                "message": "try_task_config for https://phabricator.test/D51\n"
                "Differential Diff: PHID-DIFF-testABcd12",
                "user": "code review bot <release-mgmt-analysis@mozilla.com>",
            },
        ),
        # Push to try
        "tip",
        (
            "push",
            {
                "dest": b"ssh://hg.mozilla.org/try",
                "force": True,
                "rev": b"test_tip",
                "ssh": f'ssh -o StrictHostKeyChecking="no" -o User="reviewbot@mozilla.com" -o IdentityFile="{ssh_key_path}"'.encode(),
            },
        ),
    ]

    # Reset settings for following tests
    mock_config.mercurial_cache = None
    mock_config.ssh_key = None


def test_publish_analysis_phabricator_duplicate_harbormaster_uri():
    """
    When create_harbormaster_uri raises a ConduitError due to a duplicate key
    (e.g. on task retry after worker shutdown), the error should be swallowed
    and a warning logged instead of crashing the publication task.
    """
    build = mock.MagicMock()
    build.target_phid = "PHID-HMBT-test"
    build.missing_base_revision = False

    phabricator_api = mock.MagicMock()
    phabricator_api.create_harbormaster_uri.side_effect = ConduitError(
        "Duplicate entry",
        error_code="ERR-CONDUIT-CORE",
        error_info="Duplicate entry 'uri-VEVIsJOfD0wc' for key 'harbormaster_buildartifact.key_artifact'",
    )

    payload = ("success", build, {"treeherder_url": "https://treeherder.mozilla.org/"})
    publish_analysis_phabricator(payload, phabricator_api)

    phabricator_api.create_harbormaster_uri.assert_called_once()


def test_publish_analysis_phabricator_reraises_other_conduit_errors():
    """
    Non-duplicate ConduitErrors must still propagate.
    """
    build = mock.MagicMock()
    build.target_phid = "PHID-HMBT-test"
    build.missing_base_revision = False

    phabricator_api = mock.MagicMock()
    phabricator_api.create_harbormaster_uri.side_effect = ConduitError(
        "Some other error",
        error_code="ERR-CONDUIT-CORE",
        error_info="Some unrelated error",
    )

    payload = ("success", build, {"treeherder_url": "https://treeherder.mozilla.org/"})
    with pytest.raises(ConduitError):
        publish_analysis_phabricator(payload, phabricator_api)


@pytest.mark.parametrize("missing_base", [False, True])
def test_publish_analysis_phabricator_git_failure(missing_base):
    """A fail:git worker output marks the Phabricator build as failed."""
    build = mock.MagicMock()
    build.target_phid = "PHID-HMBT-test"
    build.missing_base_revision = missing_base
    build.base_revision = "abcdef123456"

    phabricator_api = mock.MagicMock()
    payload = ("fail:git", build, {"message": "git apply failed", "duration": 1})
    publish_analysis_phabricator(payload, phabricator_api)

    phabricator_api.update_build_target.assert_called_once()
    args, kwargs = phabricator_api.update_build_target.call_args
    assert args == ("PHID-HMBT-test", BuildState.Fail)
    unit = kwargs["unit"][0]
    assert unit["name"] == "git"
    assert unit["result"] == "fail"
    assert "failed to apply your patch" in unit["details"]
    # The missing parent revision is only mentioned when it is the cause
    assert ("abcdef123456" in unit["details"]) is missing_base


def test_publish_analysis_lando_git_failure():
    """A fail:git worker output publishes the patch failure warning to Lando."""
    build = PhabricatorRevisionBuild(mock.MagicMock(), mock.MagicMock())
    build.revision = {"id": 51}
    build.diff_id = 42

    lando_api = mock.MagicMock()
    publish_analysis_lando(("fail:git", build, {}), lando_api)

    lando_api.add_warning.assert_called_once_with(LANDO_FAILURE_HG_MESSAGE, 51, 42)


def test_repository_conf_repo_type():
    """repo_type is optional, defaults to hg, and can be set to git (additive)."""
    conf = RepositoryConf(
        name="mozilla-central",
        try_name="try",
        url="https://hg.mozilla.org/mozilla-central",
        try_url="ssh://hg.mozilla.org/try",
        decision_env_prefix="GECKO",
        ssh_user="reviewbot@mozilla.com",
    )
    assert conf.repo_type == "hg"
    assert conf._replace(repo_type="git").repo_type == "git"


@pytest.mark.parametrize(
    "repo_type, uses_git, git_ssh_key",
    [
        ("git", True, "GitDeployKey"),
        ("git", True, None),
        ("hg", False, None),
    ],
)
def test_start_analysis_selects_backend(
    mock_phabricator,
    mock_workflow,
    mock_config,
    tmpdir,
    monkeypatch,
    repo_type,
    uses_git,
    git_ssh_key,
):
    """start_analysis picks the Git or Mercurial backend from repo_type."""
    mock_config.mercurial_cache = tmpdir
    mock_config.git_cache = tmpdir
    mock_config.ssh_key = "Dummy Private SSH Key"
    mock_config.git_ssh_key = git_ssh_key

    # Force the configured repository's backend type
    mock_config.repositories = [
        conf._replace(repo_type=repo_type) for conf in mock_config.repositories
    ]

    # Build never expires so the analysis proceeds
    monkeypatch.setattr(PhabricatorActions, "is_expired_build", lambda _, build: False)

    # Replace both backends with mocks so nothing clones or pushes for real
    git_repo, git_worker = MagicMock(), MagicMock()
    hg_repo, hg_worker = MagicMock(), MagicMock()
    monkeypatch.setattr(workflow_module, "GitRepository", git_repo)
    monkeypatch.setattr(workflow_module, "GitWorker", git_worker)
    monkeypatch.setattr(workflow_module, "Repository", hg_repo)
    monkeypatch.setattr(workflow_module, "MercurialWorker", hg_worker)
    git_worker.return_value.run.return_value = ("success", MagicMock(), {})
    hg_worker.return_value.run.return_value = ("success", MagicMock(), {})

    # Skip Phabricator/Lando publication of the (mocked) output
    mock_workflow.update_build = False

    with mock_phabricator as api:
        mock_workflow.phabricator = api
        revision = PhabricatorRevision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
        )
        mock_workflow.start_analysis(revision)

    if uses_git:
        assert git_repo.called and git_worker.called
        assert not hg_repo.called and not hg_worker.called
        # Git path uses the git cache, not the mercurial one
        assert git_repo.call_args.kwargs["cache_root"] == mock_config.git_cache
        # The dedicated deploy key wins, falling back to the global key
        expected_key = git_ssh_key or "Dummy Private SSH Key"
        assert git_repo.call_args.kwargs["config"]["ssh_key"] == expected_key
    else:
        assert hg_repo.called and hg_worker.called
        assert not git_repo.called and not git_worker.called
        assert hg_repo.call_args.kwargs["config"]["ssh_key"] == "Dummy Private SSH Key"

    # Reset settings for following tests
    mock_config.mercurial_cache = None
    mock_config.git_cache = None
    mock_config.ssh_key = None
    mock_config.git_ssh_key = None
