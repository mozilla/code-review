# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import tempfile

from code_review_bot import mercurial
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
