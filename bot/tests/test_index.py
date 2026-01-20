# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

from code_review_bot.config import TaskCluster
from code_review_bot.revisions import PhabricatorRevision


class MockPhabricatorRevision(PhabricatorRevision):
    """
    Fake revision to easily set properties
    """

    def __init__(self, namespaces, details, repository):
        self._namespaces = namespaces
        self._details = details
        self.base_repository = repository

    @property
    def namespaces(self):
        return self._namespaces

    def as_dict(self):
        return self._details


def test_taskcluster_index(mock_config, mock_workflow, mock_try_task):
    """
    Test the Taskcluster indexing API
    by mocking an online taskcluster state
    """

    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = MockPhabricatorRevision(
        namespaces=["mock.1234"],
        details={"id": "1234", "someData": "mock", "state": "done"},
        repository="test-repo",
    )
    mock_workflow.index(rev, test="dummy")

    assert mock_workflow.index_service.insertTask.call_count == 2
    calls = mock_workflow.index_service.insertTask.call_args_list

    # First call with namespace
    namespace, args = calls[0][0]
    assert namespace == "project.relman.test.code-review.mock.1234"
    assert args["taskId"] == "12345deadbeef"
    assert args["data"]["test"] == "dummy"
    assert args["data"]["id"] == "1234"
    assert args["data"]["source"] == "try"
    assert args["data"]["try_task_id"] == "remoteTryTask"
    assert args["data"]["try_group_id"] == "remoteTryGroup"
    assert args["data"]["repository"] == "test-repo"
    assert args["data"]["someData"] == "mock"
    assert "indexed" in args["data"]

    # Second call with sub namespace
    namespace, args = calls[1][0]
    assert namespace == "project.relman.test.code-review.mock.1234.12345deadbeef"
    assert args["taskId"] == "12345deadbeef"
    assert args["data"]["test"] == "dummy"
    assert args["data"]["id"] == "1234"
    assert args["data"]["source"] == "try"
    assert args["data"]["try_task_id"] == "remoteTryTask"
    assert args["data"]["try_group_id"] == "remoteTryGroup"
    assert args["data"]["repository"] == "test-repo"
    assert args["data"]["someData"] == "mock"
    assert "indexed" in args["data"]


def test_index_autoland(
    mock_autoland_task,
    mock_phabricator,
    mock_hgmo,
    mock_config,
    mock_workflow,
    mock_taskcluster_date,
):
    """
    Check the Taskcluster index generated for an autoland task
    """

    with mock_phabricator as api:
        revision = PhabricatorRevision.from_decision_task(mock_autoland_task, api)

    mock_workflow.index_service = mock.Mock()
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)

    mock_workflow.index(revision, state="unit-test")

    assert mock_workflow.index_service.insertTask.call_count == 2
    calls = mock_workflow.index_service.insertTask.call_args_list

    assert [c[0][0] for c in calls] == [
        "project.relman.test.code-review.head_repo.integration-autoland.deadbeef123",
        "project.relman.test.code-review.head_repo.integration-autoland.deadbeef123.12345deadbeef",
    ]

    # Check all calls have the same shared payload
    payload = {
        "base_changeset": "123deadbeef",
        "base_repository": "https://hg.mozilla.org/mozilla-unified",
        "bugzilla_id": None,
        "diff_id": None,
        "diff_phid": None,
        "has_clang_files": False,
        "head_changeset": "deadbeef123",
        "head_repository": "https://hg.mozilla.org/integration/autoland",
        "id": None,
        "indexed": "2025-10-30T00:00:00.00Z",
        "mercurial_revision": "deadbeef123",
        "monitoring_restart": False,
        "phid": None,
        "repository": "https://hg.mozilla.org/mozilla-unified",
        "source": "try",
        "state": "unit-test",
        "target_repository": "https://hg.mozilla.org/mozilla-unified",
        "title": "Changeset deadbeef123 (https://hg.mozilla.org/integration/autoland)",
        "try_group_id": "remoteTryGroup",
        "try_task_id": "remoteTryTask",
        "url": None,
    }
    assert all([c[0][1]["data"] == payload for c in calls])


def test_index_phabricator(
    mock_phabricator, mock_workflow, mock_config, mock_taskcluster_date
):
    """
    Check the Taskcluster index generated for a task triggered by Phabricator
    """

    with mock_phabricator as api:
        revision = PhabricatorRevision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
        )

    mock_workflow.index_service = mock.Mock()
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)

    mock_workflow.index(revision, state="unit-test")

    assert mock_workflow.index_service.insertTask.call_count == 8
    calls = mock_workflow.index_service.insertTask.call_args_list

    assert [c[0][0] for c in calls] == [
        "project.relman.test.code-review.phabricator.51",
        "project.relman.test.code-review.phabricator.diff.42",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-testABcd12",
        "project.relman.test.code-review.phabricator.51.12345deadbeef",
        "project.relman.test.code-review.phabricator.diff.42.12345deadbeef",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz.12345deadbeef",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-testABcd12.12345deadbeef",
    ]

    # Check all calls have the same shared payload
    payload = {
        "base_changeset": "default",
        "base_repository": "https://hg.mozilla.org/mozilla-central",
        "bugzilla_id": 1234567,
        "diff_id": 42,
        "diff_phid": "PHID-DIFF-testABcd12",
        "has_clang_files": False,
        "head_changeset": None,
        "head_repository": None,
        "id": 51,
        "indexed": "2025-10-30T00:00:00.00Z",
        "mercurial_revision": None,
        "monitoring_restart": False,
        "phid": "PHID-DREV-zzzzz",
        "repository": "https://hg.mozilla.org/mozilla-central",
        "source": "try",
        "state": "unit-test",
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "try_group_id": "remoteTryGroup",
        "try_task_id": "remoteTryTask",
        "url": "https://phabricator.test/D51",
    }
    assert all([c[0][1]["data"] == payload for c in calls])


def test_index_from_try(
    mock_phabricator,
    phab,
    mock_try_task,
    mock_decision_task,
    mock_workflow,
    mock_config,
    mock_taskcluster_date,
):
    """
    Check the Taskcluster index generated for a task triggered by end of try push
    """

    with mock_phabricator as api:
        revision = PhabricatorRevision.from_try_task(
            mock_try_task, mock_decision_task, api
        )

    mock_workflow.index_service = mock.Mock()
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)

    mock_workflow.index(revision, state="unit-test")

    assert mock_workflow.index_service.insertTask.call_count == 10
    calls = mock_workflow.index_service.insertTask.call_args_list

    assert [c[0][0] for c in calls] == [
        "project.relman.test.code-review.phabricator.51",
        "project.relman.test.code-review.phabricator.diff.42",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-test",
        "project.relman.test.code-review.head_repo.try.deadc0ffee",
        "project.relman.test.code-review.phabricator.51.12345deadbeef",
        "project.relman.test.code-review.phabricator.diff.42.12345deadbeef",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz.12345deadbeef",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-test.12345deadbeef",
        "project.relman.test.code-review.head_repo.try.deadc0ffee.12345deadbeef",
    ]

    # Check all calls have the same shared payload
    payload = {
        "base_changeset": "c0ffeedead",
        "base_repository": "https://hg.mozilla.org/mozilla-central",
        "bugzilla_id": 1234567,
        "diff_id": 42,
        "diff_phid": "PHID-DIFF-test",
        "has_clang_files": False,
        "head_changeset": "deadc0ffee",
        "head_repository": "https://hg.mozilla.org/try",
        "id": 51,
        "indexed": "2025-10-30T00:00:00.00Z",
        "mercurial_revision": "deadc0ffee",
        "monitoring_restart": False,
        "phid": "PHID-DREV-zzzzz",
        "repository": "https://hg.mozilla.org/mozilla-central",
        "source": "try",
        "state": "unit-test",
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "try_group_id": "remoteTryGroup",
        "try_task_id": "remoteTryTask",
        "url": "https://phabricator.test/D51",
    }
    assert all([c[0][1]["data"] == payload for c in calls])
