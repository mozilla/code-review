# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

from code_review_bot.config import TaskCluster
from code_review_bot.revisions import Revision


class MockRevision(Revision):
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
    rev = MockRevision(
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
    mock_autoland_task, mock_phabricator, mock_hgmo, mock_config, mock_workflow
):
    """
    Check the Taskcluster index generated for an autoland task
    """

    with mock_phabricator as api:
        revision = Revision.from_decision_task(mock_autoland_task, api)

    mock_workflow.index_service = mock.Mock()
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)

    mock_workflow.index(revision, state="unit-test")

    assert mock_workflow.index_service.insertTask.call_count == 4
    calls = mock_workflow.index_service.insertTask.call_args_list

    assert [c[0][0] for c in calls] == [
        "project.relman.test.code-review.head_repo.integration-autoland.deadbeef123",
        "project.relman.test.code-review.base_repo.mozilla-unified.123deadbeef",
        "project.relman.test.code-review.head_repo.integration-autoland.deadbeef123.12345deadbeef",
        "project.relman.test.code-review.base_repo.mozilla-unified.123deadbeef.12345deadbeef",
    ]


def test_index_phabricator(mock_phabricator, mock_workflow, mock_config):
    """
    Check the Taskcluster index generated for a task triggered by Phabricator
    """

    with mock_phabricator as api:
        revision = Revision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
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
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-testABcd12",
        "project.relman.test.code-review.base_repo.mozilla-central.default",
        "project.relman.test.code-review.phabricator.51.12345deadbeef",
        "project.relman.test.code-review.phabricator.diff.42.12345deadbeef",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz.12345deadbeef",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-testABcd12.12345deadbeef",
        "project.relman.test.code-review.base_repo.mozilla-central.default.12345deadbeef",
    ]


def test_index_from_try(
    mock_phabricator,
    phab,
    mock_try_task,
    mock_decision_task,
    mock_workflow,
    mock_config,
):
    """
    Check the Taskcluster index generated for a task triggered by end of try push
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)

    mock_workflow.index_service = mock.Mock()
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)

    mock_workflow.index(revision, state="unit-test")

    assert mock_workflow.index_service.insertTask.call_count == 12
    calls = mock_workflow.index_service.insertTask.call_args_list

    assert [c[0][0] for c in calls] == [
        "project.relman.test.code-review.phabricator.51",
        "project.relman.test.code-review.phabricator.diff.42",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-test",
        "project.relman.test.code-review.head_repo.try.deadc0ffee",
        "project.relman.test.code-review.base_repo.mozilla-central.c0ffeedead",
        "project.relman.test.code-review.phabricator.51.12345deadbeef",
        "project.relman.test.code-review.phabricator.diff.42.12345deadbeef",
        "project.relman.test.code-review.phabricator.phabricator_phid.PHID-DREV-zzzzz.12345deadbeef",
        "project.relman.test.code-review.phabricator.diffphid.PHID-DIFF-test.12345deadbeef",
        "project.relman.test.code-review.head_repo.try.deadc0ffee.12345deadbeef",
        "project.relman.test.code-review.base_repo.mozilla-central.c0ffeedead.12345deadbeef",
    ]
