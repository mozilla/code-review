# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os.path
import re
import urllib.parse
import uuid
from collections import defaultdict
from collections import namedtuple
from contextlib import contextmanager

import pytest
import responses
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import stats
from code_review_bot.backend import BackendAPI
from code_review_bot.config import settings
from code_review_bot.tasks.coverity import CoverityIssue

MOCK_DIR = os.path.join(os.path.dirname(__file__), "mocks")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

MockArtifactResponse = namedtuple("MockArtifactResponse", "content")


@pytest.fixture(scope="function")
def mock_repositories():
    return [
        {
            "url": "https://hg.mozilla.org/mozilla-central",
            "decision_env_revision": "GECKO_HEAD_REV",
            "decision_env_repository": "GECKO_HEAD_REPOSITORY",
            "checkout": "robust",
            "try_url": "ssh://hg.mozilla.org/try",
            "try_mode": "json",
            "name": "mozilla-central",
            "ssh_user": "reviewbot@mozilla.com",
        }
    ]


@pytest.fixture(scope="function")
def mock_config(mock_repositories):
    """
    Mock configuration for bot
    Using try source
    """
    # Make sure we are running in local mode
    if "TASK_ID" in os.environ:
        del os.environ["TASK_ID"]
    os.environ["TRY_TASK_ID"] = "remoteTryTask"
    os.environ["TRY_TASK_GROUP_ID"] = "remoteTryGroup"
    settings.setup("test", ["dom/*", "tests/*.py", "test/*.c"], mock_repositories)
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
            self.analyzer = "mock-analyzer"

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
def mock_coverity_issues(mock_revision,):
    """
    Build a list of Coverity issues
    """

    return [
        CoverityIssue(
            "mock-coverity",
            mock_revision,
            {
                "reliability": "high",
                "line": i,
                "build_error": True,
                "message": "Unidentified symbol",
                "extra": {"category": "bug", "stateOnServer": []},
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

    def diff_search(request):
        payload = dict(urllib.parse.parse_qsl(request.body))
        assert "params" in payload
        params = json.loads(payload["params"])

        name = ["diff_search"]
        for values in params.get("constraints", {}).values():
            name += values

        content = _response("_".join(name))

        return (200, {"Content-Type": "application/json"}, content)

    responses.add(
        responses.POST,
        "http://phabricator.test/api/user.whoami",
        body=_response("auth"),
        content_type="application/json",
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.diff.search",
        callback=diff_search,
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

    responses.add(
        responses.POST,
        "http://phabricator.test/api/diffusion.repository.search",
        body=_response("repository_search"),
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
def mock_autoland_task():
    """
    Mock a remote Autoland decision task definition
    """
    return {
        "payload": {
            "env": {
                "GECKO_BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-unified",
                "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/integration/autoland",
                "GECKO_HEAD_REF": "deadbeef123",
                "GECKO_HEAD_REV": "deadbeef123",
            }
        }
    }


@pytest.fixture
def mock_revision(mock_phabricator, mock_try_task, mock_config):
    """
    Mock a mercurial revision
    """
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        return Revision.from_try(mock_try_task, api)


class MockQueue(object):
    """
    Mock the Taskcluster queue, by using fake tasks descriptions, relations and artifacts
    """

    _artifacts = {}

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

    def listLatestArtifacts(self, task_id):
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

        self._artifacts[task_id]["artifacts"].append(payload)
        return {
            "storageType": "s3",
            "putUrl": "http://storage.test/{}".format(name),
            "contentType": payload["contentType"],
        }


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


class MockNotify(object):
    emails = []

    def email(self, payload):
        self.emails.append(payload)


@pytest.fixture(scope="function")
def mock_backend_secret(mock_taskcluster_config):
    """
    Mock the taskcluster secret needed for backend storage
    """
    mock_taskcluster_config.secrets = {
        "backend": {
            "url": "http://code-review-backend.test",
            "username": "tester",
            "password": "test1234",
        }
    }


@pytest.fixture
def mock_workflow(mock_config, mock_phabricator, mock_taskcluster_config):
    """
    Mock the workflow along with Taskcluster mocks
    No phabricator output here
    """
    from code_review_bot.workflow import Workflow

    # Reset stats on new workflow
    stats.metrics = []

    # Default empty secrets
    mock_taskcluster_config.secrets = {}

    class MockWorkflow(Workflow):
        def __init__(self):
            self.reporters = {}
            self.phabricator_api = None
            self.index_service = mock_taskcluster_config.get_service("index")
            self.queue_service = mock_taskcluster_config.get_service("queue")
            self.zero_coverage_enabled = True
            self.backend_api = BackendAPI()
            self.update_build = False
            self.task_failures_ignored = []

        def setup_mock_tasks(self, tasks):
            """
            Add mock tasks in queue & index mock services
            """
            # The task group id is used to find the decision task
            # as it's the task with the same ID as the group
            mock_config.try_group_id = "decision"
            self.index_service.configure(tasks)
            self.queue_service.configure(tasks)

        def update_status(self, revision, state):
            # Store last known state on revision
            revision._state = state

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

    # Shared instance by fixture
    queue = MockQueue()
    index = MockIndex()
    notify = MockNotify()

    def _get_service(name):
        if name == "queue":
            return queue
        elif name == "index":
            return index
        elif name == "notify":
            return notify
        else:
            raise NotImplementedError

    taskcluster.get_service = _get_service

    return taskcluster


@pytest.fixture
def mock_hgmo():
    """
    Mock HGMO raw-file response to build a issue hash
    """

    def fake_raw_file(request):
        repo, _, revision, *path = request.path_url[1:].split("/")
        path = "/".join(path)

        mock_path = os.path.join(MOCK_DIR, f"hgmo_{path}")
        if os.path.exists(mock_path):
            # Read existing mock file
            with open(mock_path) as f:
                content = f.read()
        else:
            # Produce a long fake file
            content = "\n".join(f"{repo}:{revision}:{path}:{i+1}" for i in range(1000))

        return (200, {}, content)

    def fake_json_rev(request):
        *repo, _, revision = request.path_url[1:].split("/")
        repo = "-".join(repo)

        mock_path = os.path.join(MOCK_DIR, f"hgmo_{repo}_{revision}.json")
        content = open(mock_path).read()

        return (200, {"Content-Type": "application/json"}, content)

    responses.add_callback(
        responses.GET,
        re.compile(r"^https?://(hgmo|hg\.mozilla\.org)/[\w-]+/raw-file/.*"),
        callback=fake_raw_file,
    )
    responses.add_callback(
        responses.GET,
        re.compile(r"^https?://(hgmo|hg\.mozilla\.org)/[\w\-\/]+/json-rev/(\w+)"),
        callback=fake_json_rev,
    )


@pytest.fixture(scope="function")
def mock_backend(mock_backend_secret):
    """
    Mock the code review backend endpoints
    """
    host = "code-review-backend.test"

    revisions = {}
    diffs = {}
    issues = defaultdict(list)

    def get_revision(request):
        """Get a revision when available in db"""
        revision_id = int(request.path_url.split("/")[3])
        if revision_id in revisions:
            return (200, {}, json.dumps(revisions[revision_id]))
        return (404, {}, "")

    def post_revision(request):
        """Create a revision when not available in db"""
        payload = json.loads(request.body)
        revision_id = payload["id"]
        if revision_id in revisions:
            return (400, {}, "")

        # Add diffs_url to the output
        payload["diffs_url"] = f"http://{host}/v1/revision/{revision_id}/diffs/"

        revisions[revision_id] = payload
        return (201, {}, json.dumps(payload))

    def get_diff(request):
        """Get a diff when available in db"""
        diff_id = int(request.path_url.split("/")[5])
        if diff_id in diffs:
            return (200, {}, json.dumps(diffs[diff_id]))
        return (404, {}, "")

    def post_diff(request):
        """Create a diff when not available in db"""
        payload = json.loads(request.body)
        diff_id = payload["id"]
        if diff_id in diffs:
            return (400, {}, "")
        diffs[diff_id] = payload

        # Add issues_url to the output
        payload["issues_url"] = f"http://{host}/v1/diff/{diff_id}/issues/"

        return (201, {}, json.dumps(payload))

    def post_issue(request):
        """Create a issue when not available in db"""
        diff_id = int(request.path_url.split("/")[3])
        payload = json.loads(request.body)

        # Add a constant uuid as issue id
        payload["id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, request.url + str(len(issues[diff_id])))
        )

        issues[diff_id].append(payload)
        return (201, {}, json.dumps(payload))

    # Revision
    responses.add_callback(
        responses.GET,
        re.compile(rf"^http://{host}/v1/revision/(\d+)/$"),
        callback=get_revision,
    )
    responses.add_callback(
        responses.POST,
        re.compile(f"^http://{host}/v1/revision/$"),
        callback=post_revision,
    )

    # Diff
    responses.add_callback(
        responses.GET,
        re.compile(rf"^http://{host}/v1/revision/(\d+)/diffs/(\d+)/$"),
        callback=get_diff,
    )
    responses.add_callback(
        responses.POST,
        re.compile(rf"^http://{host}/v1/revision/(\d+)/diffs/$"),
        callback=post_diff,
    )

    # Issues
    responses.add_callback(
        responses.POST,
        re.compile(rf"^http://{host}/v1/diff/(\d+)/issues/$"),
        callback=post_issue,
    )

    return revisions, diffs, issues


@pytest.fixture
def mock_treeherder():
    responses.add(
        responses.GET,
        "https://treeherder.mozilla.org/api/jobdetail/",
        body=json.dumps({"results": [{"job_id": 1234}]}),
        content_type="application/json",
    )
