# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os.path
import time
from unittest.mock import MagicMock

import hglib
import responses
from conftest import MockBuild
from libmozdata.phabricator import PhabricatorPatch

from code_review_bot import mercurial

MERCURIAL_FAILURE = """unable to find 'crash.txt' for patching
(use '--prefix' to apply patch relative to the current directory)
1 out of 1 hunks FAILED -- saving rejects to file crash.txt.rej
abort: patch failed to apply
"""


class STDOutputMock:
    def fileno(self):
        return 4

    content = ""


class PopenMock:
    stdout = STDOutputMock()
    stderr = STDOutputMock()
    returncode = 0

    def poll(self):
        return True

    def communicate(self):
        out = self.stdout.content = "Hello world"
        err = self.stderr.content = "An error occurred"
        return out, err

    def __call__(self, command):
        self.command = command
        return self


def test_hg_run(monkeypatch):
    popen_mock = PopenMock()
    monkeypatch.setattr("hglib.util.popen", popen_mock)
    mercurial.hg_run(["checkout", "https://hg.repo/", "--test"])
    assert popen_mock.command == ["hg", "checkout", "https://hg.repo/", "--test"]
    assert popen_mock.stdout.content == "Hello world"
    assert popen_mock.stderr.content == "An error occurred"


def test_robustcheckout(monkeypatch):
    popen_mock = PopenMock()
    monkeypatch.setattr("hglib.util.popen", popen_mock)

    mercurial.robust_checkout(
        repo_url="https://hg.repo/try",
        repo_upstream_url="https://hg.repo/mc",
        revision="deadbeef1234",
        checkout_dir="/tmp/checkout",
        sharebase_dir="/tmp/shared",
    )

    assert popen_mock.command == [
        "hg",
        "robustcheckout",
        b"--purge",
        b"--sharebase=/tmp/shared",
        b"--revision=deadbeef1234",
        b"--upstream=https://hg.repo/mc",
        b"--",
        "https://hg.repo/try",
        "/tmp/checkout",
    ]


def test_push_to_try(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    with a push to try server
    """
    # Preload the build
    diff = {
        "phid": "PHID-DIFF-test123",
        "revisionPHID": "PHID-DREV-deadbeef",
        "id": 1234,
        # Revision does not exist, will apply on tip
        "baseRevision": "abcdef12345",
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_mc.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker()
    result = worker.run(mock_mc, build)

    # Check the treeherder link was generated
    tip = mock_mc.repo.tip()
    assert result == (
        "success",
        build,
        {
            "revision": tip.node.decode("utf-8"),
            "treeherder_url": "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
                tip.node.decode("utf-8")
            ),
        },
    )

    # The target should have content now
    assert os.path.exists(target)
    assert open(target).read() == "First Line\nSecond Line\n"

    # Check the try_task_config file
    assert os.path.exists(config)
    assert json.load(open(config)) == {
        "version": 2,
        "parameters": {
            "target_tasks_method": "codereview",
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-deadbeef",
        },
    }

    # Get tip commit in repo
    # It should be different from the initial one (patches + config have applied)
    assert tip.node != initial.node

    # Check all commits messages
    assert [c.desc for c in mock_mc.repo.log()] == [
        b"try_task_config for code-review\nDifferential Diff: PHID-DIFF-test123",
        b"Bug XXX - A second commit message\nDifferential Diff: PHID-DIFF-test123",
        b"Bug XXX - A first commit message\nDifferential Diff: PHID-DIFF-xxxx",
        b"Readme",
    ]

    # Check all commits authors
    assert [c.author for c in mock_mc.repo.log()] == [
        b"code review bot <release-mgmt-analysis@mozilla.com>",
        b"John Doe <john@allizom.org>",
        b"randomUsername <random>",
        b"test",
    ]

    # Check the push to try has been called
    # with tip commit
    ssh_conf = f'ssh -o StrictHostKeyChecking="no" -o User="john@doe.com" -o IdentityFile="{mock_mc.ssh_key_path}"'
    mock_mc.repo.push.assert_called_with(
        dest=b"http://mozilla-central/try",
        force=True,
        rev=tip.node,
        ssh=ssh_conf.encode("utf-8"),
    )


def test_push_to_try_existing_rev(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    with a push to try server
    but applying on an existing revision
    """
    repo_dir = mock_mc.repo.root().decode("utf-8")

    def _readme(content):
        # Make a commit on README.md in the repo
        readme = os.path.join(repo_dir, "README.md")
        with open(readme, "a") as f:
            f.write(content)
        _, rev = mock_mc.repo.commit(message=content.encode("utf-8"), user=b"test")
        return rev

    # Make two commits, the first one is our base
    base = _readme("Local base for diffs")
    extra = _readme("EXTRA")

    # Preload the build
    diff = {
        "phid": "PHID-DIFF-solo",
        "revisionPHID": "PHID-DREV-solo",
        "id": 9876,
        # Revision does not exist, will apply on tip
        "baseRevision": base,
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", diff)
    build.revision_url = "http://phab.test/D1234"
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # The patched and config files should not exist at first
    target = os.path.join(repo_dir, "solo.txt")
    config = os.path.join(repo_dir, "try_task_config.json")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_mc, build)

    # Check the treeherder link was queued
    tip = mock_mc.repo.tip()
    assert mode == "success"
    assert out_build == build
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        tip.node.decode("utf-8")
    )
    assert details["revision"] == tip.node.decode("utf-8")

    # The target should have content now
    assert os.path.exists(target)
    assert open(target).read() == "Solo PATCH\n"

    # Check the try_task_config file
    assert os.path.exists(config)
    assert json.load(open(config)) == {
        "version": 2,
        "parameters": {
            "target_tasks_method": "codereview",
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-deadbeef",
        },
    }

    # Get tip commit in repo
    # It should be different from the initial one (patches and config have applied)
    assert tip.node != base
    assert (
        tip.desc
        == b"""try_task_config for http://phab.test/D1234
Differential Diff: PHID-DIFF-solo"""
    )

    # Check the push to try has been called
    # with tip commit
    ssh_conf = f'ssh -o StrictHostKeyChecking="no" -o User="john@doe.com" -o IdentityFile="{mock_mc.ssh_key_path}"'
    mock_mc.repo.push.assert_called_with(
        dest=b"http://mozilla-central/try",
        force=True,
        rev=tip.node,
        ssh=ssh_conf.encode("utf-8"),
    )

    # Check the parent is the solo patch commit
    parents = mock_mc.repo.parents(tip.node)
    assert len(parents) == 1
    parent = parents[0]
    assert (
        parent.desc
        == b"A nice human readable commit message\nDifferential Diff: PHID-DIFF-solo"
    )

    # Check the grand parent is the base, not extra
    great_parents = mock_mc.repo.parents(parent.node)
    assert len(great_parents) == 1
    # TODO: Re-enable base revision identification after https://github.com/mozilla/libmozevent/issues/110.
    # great_parent = great_parents[0]
    # assert great_parent.node == base

    # Extra commit should not appear
    assert parent.node != extra
    # TODO: Re-enable base revision identification after https://github.com/mozilla/libmozevent/issues/110.
    # assert great_parent.node != extra
    # assert "EXTRA" not in open(os.path.join(repo_dir, "README.md")).read()


def test_dont_push_skippable_files_to_try(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    that skips the push to try server
    """

    # Preload the build
    diff = {
        "phid": "PHID-DIFF-test123",
        "revisionPHID": "PHID-DREV-deadbeef",
        "id": 1234,
        # Revision does not exist, will apply on tip
        "baseRevision": "abcdef12345",
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_mc.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker(
        skippable_files=["test.txt"],
    )
    mode, out_build, details = worker.run(mock_mc, build)

    # Check the treeherder link was queued
    tip = mock_mc.repo.tip()
    assert mode == "fail:ineligible"
    assert out_build == build
    assert (
        details["message"]
        == "Modified files match skippable internal configuration files"
    )

    # The target should have content now
    assert os.path.exists(target)
    assert open(target).read() == "First Line\nSecond Line\n"

    # Get tip commit in repo
    # It should be different from the initial one (patches + config have applied)
    assert tip.node != initial.node

    # Check all commits messages
    assert [c.desc for c in mock_mc.repo.log()] == [
        b"Bug XXX - A second commit message\nDifferential Diff: PHID-DIFF-test123",
        b"Bug XXX - A first commit message\nDifferential Diff: PHID-DIFF-xxxx",
        b"Readme",
    ]

    # Check all commits authors
    assert [c.author for c in mock_mc.repo.log()] == [
        b"John Doe <john@allizom.org>",
        b"randomUsername <random>",
        b"test",
    ]

    # Check the push to try has not been called
    mock_mc.repo.push.assert_not_called()


def test_treeherder_link(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    and check the treeherder link publication as an artifact
    """
    # Preload the build
    diff = {
        "phid": "PHID-DIFF-test123",
        "revisionPHID": "PHID-DREV-deadbeef",
        "id": 1234,
        "baseRevision": "abcdef12345",
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-somehash", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_mc.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_mc, build)

    # Check the treeherder link was queued
    tip = mock_mc.repo.tip()
    assert mode == "success"
    assert out_build == build
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        tip.node.decode("utf-8")
    )
    assert details["revision"] == tip.node.decode("utf-8")

    # Tip should be updated
    assert tip.node != initial.node


def test_failure_general(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    and check the treeherder link publication as an artifact
    Use a Python common exception to trigger a broken build
    """
    diff = {
        "phid": "PHID-DIFF-test123",
        "id": 1234,
        "baseRevision": None,
        "revisionPHID": "PHID-DREV-deadbeef",
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-somehash", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_mc.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    # Raise an exception during the workflow to trigger a broken build
    def boom(*args):
        raise Exception("Boom")

    mock_mc.apply_build = boom

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_mc, build)

    # Check the unit result was published

    assert mode == "fail:general"
    assert out_build == build
    assert details["duration"] > 0
    assert details["message"] == "Boom"

    # Clone should not be modified
    tip = mock_mc.repo.tip()
    assert tip.node == initial.node


def test_failure_mercurial(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    and check the treeherder link publication as an artifact
    Apply a bad mercurial patch to trigger a mercurial fail
    """
    diff = {
        "revisionPHID": "PHID-DREV-666",
        "baseRevision": "missing",
        "phid": "PHID-DIFF-666",
        "id": 666,
    }
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-build-666", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_mc.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_mc, build)

    # Check the treeherder link was queued
    assert mode == "fail:mercurial"
    assert out_build == build
    assert details["duration"] > 0
    assert details["message"] == MERCURIAL_FAILURE

    # Clone should not be modified
    tip = mock_mc.repo.tip()
    assert tip.node == initial.node


def test_push_to_try_nss(PhabricatorMock, mock_nss):
    """
    Run mercurial worker on a single diff
    with a push to try server, but with NSS support (try syntax)
    """
    diff = {
        "phid": "PHID-DIFF-test123",
        "revisionPHID": "PHID-DREV-deadbeef",
        "id": 1234,
        # Revision does not exist, will apply on tip
        "baseRevision": "abcdef12345",
    }
    build = MockBuild(1234, "PHID-REPO-nss", 5678, "PHID-HMBT-deadbeef", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # Get initial tip commit in repo
    initial = mock_nss.repo.tip()

    # The patched and config files should not exist at first
    repo_dir = mock_nss.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_nss, build)

    # Check the treeherder link was queued
    tip = mock_nss.repo.tip()
    assert mode == "success"
    assert out_build == build
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        tip.node.decode("utf-8")
    )
    assert details["revision"] == tip.node.decode("utf-8")

    # The target should have content now
    assert os.path.exists(target)
    assert open(target).read() == "First Line\nSecond Line\n"

    # The config should have content now
    assert os.path.exists(config)
    assert json.load(open(config)) == {
        "version": 2,
        "parameters": {
            "optimize_target_tasks": True,
            "phabricator_diff": "PHID-HMBT-deadbeef",
            "target_tasks_method": "codereview",
        },
    }

    # Get tip commit in repo
    # It should be different from the initial one (patches + config have applied)
    assert tip.node != initial.node

    # Check all commits messages
    assert [c.desc for c in mock_nss.repo.log()] == [
        b"try_task_config for code-review\nDifferential Diff: PHID-DIFF-test123",
        b"Bug XXX - A second commit message\nDifferential Diff: PHID-DIFF-test123",
        b"Bug XXX - A first commit message\nDifferential Diff: PHID-DIFF-xxxx",
        b"Readme",
    ]

    # Check the push to try has been called
    # with tip commit
    ssh_conf = f'ssh -o StrictHostKeyChecking="no" -o User="john@doe.com" -o IdentityFile="{mock_nss.ssh_key_path}"'
    mock_nss.repo.push.assert_called_with(
        dest=b"http://nss/try", force=True, rev=tip.node, ssh=ssh_conf.encode("utf-8")
    )


def test_crash_utf8_author(PhabricatorMock, mock_mc):
    """
    Run mercurial worker on a single diff
    but the patch author has utf-8 chars in its name
    """
    diff = {
        "revisionPHID": "PHID-DREV-badutf8",
        "baseRevision": "missing",
        "phid": "PHID-DIFF-badutf8",
        "id": 555,
    }
    build = MockBuild(4444, "PHID-REPO-mc", 5555, "PHID-build-badutf8", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    # The patched and config files should not exist at first
    repo_dir = mock_mc.repo.root().decode("utf-8")
    config = os.path.join(repo_dir, "try_task_config.json")
    target = os.path.join(repo_dir, "test.txt")
    assert not os.path.exists(target)
    assert not os.path.exists(config)

    # Run the mercurial worker on that patch only
    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(mock_mc, build)

    # Check we have the patch with utf-8 author properly applied
    assert [(c.author, c.desc) for c in mock_mc.repo.log()] == [
        (
            b"code review bot <release-mgmt-analysis@mozilla.com>",
            b"try_task_config for code-review\n"
            b"Differential Diff: PHID-DIFF-badutf8",
        ),
        (
            b"Andr\xc3\xa9 XXXX <andre.xxxx@allizom.org>",
            b"This patch has an author with utf8 chars\n"
            b"Differential Diff: PHID-DIFF-badutf8",
        ),
        (b"test", b"Readme"),
    ]

    # The phab output should be successful
    assert mode == "success"
    assert out_build == build
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        mock_mc.repo.tip().node.decode("utf-8")
    )
    assert details["revision"] == mock_mc.repo.tip().node.decode("utf-8")


def test_unexpected_push_failure(PhabricatorMock, mock_mc):
    """
    When a fail occurs while pushing the file configuring try
    A new task for the build is added to the bus
    """
    diff = {
        "revisionPHID": "PHID-DREV-badutf8",
        "baseRevision": "missing",
        "phid": "PHID-DIFF-badutf8",
        "id": 555,
    }
    build = MockBuild(4444, "PHID-REPO-mc", 5555, "PHID-build-badutf8", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    from code_review_bot import mercurial

    mercurial.MAX_PUSH_RETRIES = 1
    mercurial.TRY_STATUS_URL = "http://test.status/try"
    mercurial.PUSH_RETRY_EXPONENTIAL_DELAY = 0
    mercurial.TRY_STATUS_DELAY = 0
    mercurial.TRY_STATUS_MAX_WAIT = 0

    responses.get(
        "http://test.status/try", status=200, json={"result": {"status": "open"}}
    )

    repository_mock = MagicMock(spec=mercurial.Repository)
    repository_mock.push_to_try.side_effect = [
        hglib.error.CommandError(
            args=("push", "try_url"),
            ret=1,
            err="abort: push failed on remote",
            out="",
        ),
        mock_mc.repo.tip(),
    ]
    repository_mock.try_name = "try"
    repository_mock.retries = 0

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(repository_mock, build)

    assert mode == "success"
    assert out_build == build
    tip = mock_mc.repo.tip()
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        tip.node.decode("utf-8")
    )
    assert details["revision"] == tip.node.decode("utf-8")
    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("GET", "http://test.status/try")
    ]


def test_push_failure_max_retries(PhabricatorMock, mock_mc, monkeypatch):
    """
    When a fail occurs while pushing the file configuring try
    A new task for the build is added to the bus
    """

    # Do not really sleep between retries
    sleep_history = []
    monkeypatch.setattr(time, "sleep", lambda x: sleep_history.append(x))

    diff = {
        "revisionPHID": "PHID-DREV-badutf8",
        "baseRevision": "missing",
        "phid": "PHID-DIFF-badutf8",
        "id": 555,
    }
    build = MockBuild(4444, "PHID-REPO-mc", 5555, "PHID-build-badutf8", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    from code_review_bot import mercurial

    mercurial.MAX_PUSH_RETRIES = 2
    mercurial.TRY_STATUS_URL = "http://test.status/try"
    mercurial.PUSH_RETRY_EXPONENTIAL_DELAY = 2
    mercurial.TRY_STATUS_DELAY = 0
    mercurial.TRY_STATUS_MAX_WAIT = 0

    responses.get(
        "http://test.status/try", status=200, json={"result": {"status": "open"}}
    )

    repository_mock = MagicMock(spec=mercurial.Repository)
    repository_mock.push_to_try.side_effect = hglib.error.CommandError(
        args=("push", "try_url"),
        ret=1,
        err="abort: push failed on remote",
        out="",
    )

    worker = mercurial.MercurialWorker()
    mode, out_build, details = worker.run(repository_mock, build)

    # Check the treeherder link was queued
    assert build.retries == 3

    assert mode == "fail:mercurial"
    assert out_build == build
    assert details["duration"] > 0
    assert (
        details["message"]
        == "Max number of retries has been reached pushing the build to try repository"
    )

    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("GET", "http://test.status/try"),
        ("GET", "http://test.status/try"),
    ]
    assert sleep_history == [2, 4]


def test_push_closed_try(PhabricatorMock, mock_mc, monkeypatch):
    """
    Detect when try tree is in a closed state and wait before it is opened to retry
    """

    diff = {
        "revisionPHID": "PHID-DREV-badutf8",
        "baseRevision": "missing",
        "phid": "PHID-DIFF-badutf8",
        "id": 555,
    }
    build = MockBuild(4444, "PHID-REPO-mc", 5555, "PHID-build-badutf8", diff)
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)

    from code_review_bot import mercurial

    mercurial.MAX_PUSH_RETRIES = 2
    mercurial.TRY_STATUS_URL = "http://test.status/try"
    mercurial.PUSH_RETRY_EXPONENTIAL_DELAY = 2
    mercurial.TRY_STATUS_DELAY = 42
    mercurial.TRY_STATUS_MAX_WAIT = 1

    # Do not really sleep between retries
    sleep_history = []
    monkeypatch.setattr(time, "sleep", lambda x: sleep_history.append(x))

    responses.get(
        "http://test.status/try", status=200, json={"result": {"status": "closed"}}
    )
    responses.get("http://test.status/try", status=500)
    responses.get(
        "http://test.status/try", status=200, json={"result": {"status": "open"}}
    )

    repository_mock = MagicMock(spec=mercurial.Repository)
    repository_mock.push_to_try.side_effect = [
        hglib.error.CommandError(
            args=("push", "try_url"),
            ret=1,
            err="abort: push failed on remote",
            out="",
        ),
        mock_mc.repo.tip(),
    ]
    repository_mock.try_name = "try"
    repository_mock.retries = 0

    worker = mercurial.MercurialWorker()

    mode, out_build, details = worker.run(repository_mock, build)
    assert repository_mock.push_to_try.call_count == 2

    assert mode == "success"
    assert out_build == build
    tip = mock_mc.repo.tip()
    assert details[
        "treeherder_url"
    ] == "https://treeherder.mozilla.org/#/jobs?repo=try&revision={}".format(
        tip.node.decode("utf-8")
    )
    assert details["revision"] == tip.node.decode("utf-8")
    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("GET", "http://test.status/try"),
        ("GET", "http://test.status/try"),
        ("GET", "http://test.status/try"),
    ]
    assert sleep_history == [42, 42, 2]


def test_get_base_identifier(mock_mc):
    stack = [
        PhabricatorPatch(1, "PHID-abc", "", "abc", None),
        PhabricatorPatch(2, "PHID-def", "", "def", None),
        PhabricatorPatch(3, "PHID-ghi", "", "ghi", None),
    ]

    assert (
        mock_mc.get_base_identifier(stack) == "abc"
    ), "The base commit of the stack should be returned."

    mock_mc.use_latest_revision = True

    assert (
        mock_mc.get_base_identifier(stack) == "tip"
    ), "`tip` commit should be used when `use_latest_revision` is `True`."
