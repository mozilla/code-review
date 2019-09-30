# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os.path
from collections import namedtuple
from contextlib import contextmanager

import pytest
import responses
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import stats
from code_review_bot.config import settings
from code_review_bot.tasks.coverity import CoverityIssue

MOCK_DIR = os.path.join(os.path.dirname(__file__), "mocks")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

MockArtifactResponse = namedtuple("MockArtifactResponse", "content")


@pytest.fixture(scope="function")
def mock_config():
    """
    Mock configuration for bot
    Using try source
    """
    # Make sure we are running in local mode
    if "TASK_ID" in os.environ:
        del os.environ["TASK_ID"]
    os.environ["TRY_TASK_ID"] = "remoteTryTask"
    os.environ["TRY_TASK_GROUP_ID"] = "remoteTryGroup"
    settings.setup("test", "IN_PATCH", ["dom/*", "tests/*.py", "test/*.c"])
    return settings


@pytest.fixture
def mock_issues():
    """
    Build a list of dummy issues
    """

    class MockIssue(object):
        def __init__(self, nb):
            self.nb = nb
            self.path = "/path/to/file"

        def as_markdown(self):
            return "This is the mock issue n°{}".format(self.nb)

        def as_text(self):
            return str(self.nb)

        def as_dict(self):
            return {"nb": self.nb}

        def is_publishable(self):
            return self.nb % 2 == 0

        def is_build_error(self):
            return self.nb % 4 == 0

    return [MockIssue(i) for i in range(5)]


@pytest.fixture
def mock_coverity_issues():
    """
    Build a list of Coverity issues
    """

    return [
        CoverityIssue(
            0,
            {
                "reliability": "high",
                "line": i,
                "build_error": True,
                "message": "Unidentified symbol",
                "extra": {"category": "bug", "stateOnServer": False},
                "flag": "flag",
            },
            "some/file/path",
        )
        for i in range(2)
    ]


@pytest.fixture
@contextmanager
def mock_phabricator(mock_config):
    """
    Mock phabricator authentication process
    """

    def _response(name):
        path = os.path.join(MOCK_DIR, "phabricator_{}.json".format(name))
        assert os.path.exists(path)
        return open(path).read()

    responses.add(
        responses.POST,
        "http://phabricator.test/api/user.whoami",
        body=_response("auth"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.diff.search",
        body=_response("diff_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.revision.search",
        body=_response("revision_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.query",
        body=_response("diff_query"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.getrawdiff",
        body=_response("diff_raw"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.createinline",
        body=_response("createinline"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/edge.search",
        body=_response("edge_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/transaction.search",
        body=_response("transaction_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/harbormaster.target.search",
        body=_response("target_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/harbormaster.build.search",
        body=_response("build_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/harbormaster.buildable.search",
        body=_response("buildable_search"),
        content_type="application/json",
    )

    responses.add(
        responses.POST,
        "http://phabricator.test/api/harbormaster.sendmessage",
        body=_response("send_message"),
        content_type="application/json",
    )

    yield PhabricatorAPI(url="http://phabricator.test/api/", api_key="deadbeef")


@pytest.fixture
def mock_try_task():
    """
    Mock a remote Try task definition
    """
    return {"extra": {"code-review": {"phabricator-diff": "PHID-HMBT-test"}}}


@pytest.fixture
def mock_revision(mock_phabricator, mock_try_task, mock_config):
    """
    Mock a mercurial revision
    """
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        return Revision(api, mock_try_task, update_build=False)


class MockQueue(object):
    """
    Mock the Taskcluster queue, by using fake tasks descriptions, relations and artifacts
    """

    def configure(self, relations):
        # Create tasks
        assert isinstance(relations, dict)
        self._tasks = {
            task_id: {
                "dependencies": desc.get("dependencies", []),
                "metadata": {
                    "name": desc.get("name", "source-test-mozlint-{}".format(task_id))
                },
                "payload": {
                    "image": desc.get("image", "alpine"),
                    "env": desc.get("env", {}),
                },
            }
            for task_id, desc in relations.items()
        }

        # Create status
        self._status = {
            task_id: {
                "status": {
                    "taskId": task_id,
                    "state": desc.get("state", "completed"),
                    "runs": [{"runId": 0}],
                }
            }
            for task_id, desc in relations.items()
        }

        # Create artifacts
        self._artifacts = {
            task_id: {
                "artifacts": [
                    {
                        "name": name,
                        "storageType": "dummyStorage",
                        "contentType": isinstance(artifact, (dict, list))
                        and "application/json"
                        or "text/plain",
                        "content": artifact,
                    }
                    for name, artifact in desc.get("artifacts", {}).items()
                ]
            }
            for task_id, desc in relations.items()
        }

    def task(self, task_id):
        return self._tasks[task_id]

    def status(self, task_id):
        return self._status[task_id]

    def listTaskGroup(self, group_id):
        return {
            "tasks": [
                {"task": self.task(task_id), "status": self.status(task_id)["status"]}
                for task_id in self._tasks.keys()
            ]
        }

    def listArtifacts(self, task_id, run_id):
        return self._artifacts.get(task_id, {})

    def getArtifact(self, task_id, run_id, artifact_name):
        artifacts = self._artifacts.get(task_id, {})
        if not artifacts:
            return

        artifact = next(
            filter(lambda a: a["name"] == artifact_name, artifacts["artifacts"])
        )
        if artifact["contentType"] == "application/json":
            return artifact["content"]
        return {"response": MockArtifactResponse(artifact["content"].encode("utf-8"))}

    def createArtifact(self, task_id, run_id, name, payload):
        if task_id not in self._artifacts:
            self._artifacts[task_id] = {"artifacts": []}
        payload["name"] = name
        payload["requests"] = [
            {
                "method": "PUT",
                "url": "http://storage.test/{}".format(name),
                "headers": {},
            }
        ]
        self._artifacts[task_id]["artifacts"].append(payload)
        return payload

    def completeArtifact(self, task_id, run_id, name, payload):
        assert task_id in self._artifacts
        assert "etags" in payload
        assert "test123" in payload["etags"]


class MockIndex(object):
    def configure(self, tasks):
        self.tasks = tasks

    def insertTask(self, route, payload):
        self.tasks[route] = payload

    def findTask(self, route):
        task_id = next(
            iter(
                [
                    task_id
                    for task_id, task in self.tasks.items()
                    if task.get("route") == route
                ]
            ),
            None,
        )
        if task_id is None:
            raise Exception("Task {} not found".format(route))
        return {"taskId": task_id}


@pytest.fixture
def mock_workflow(mock_phabricator):
    """
    Mock the workflow along with Taskcluster mocks
    No phabricator output here
    """
    from code_review_bot.workflow import Workflow

    # Reset stats on new workflow
    stats.metrics = []

    class MockWorkflow(Workflow):
        def __init__(self):
            self.reporters = {}
            self.phabricator_api = None
            self.index_service = MockIndex()
            self.queue_service = MockQueue()
            self.zero_coverage_enabled = True

        def setup_mock_tasks(self, tasks):
            """
            Add mock tasks in queue & index mock services
            """
            self.index_service.configure(tasks)
            self.queue_service.configure(tasks)

    return MockWorkflow()


@pytest.fixture
def mock_coverage_artifact():
    path = os.path.join(MOCK_DIR, "zero_coverage_report.json")
    return {"public/zero_coverage_report.json": json.load(open(path))}


@pytest.fixture
def mock_taskcluster_config():
    """
    Mock a taskcluster proxy usage
    """
    from code_review_bot import taskcluster

    taskcluster.options = {"rootUrl": "http://taskcluster.test"}
