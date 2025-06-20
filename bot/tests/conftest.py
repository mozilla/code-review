# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import collections
import json
import os.path
import re
import tempfile
import urllib
import urllib.parse
import uuid
from collections import defaultdict, namedtuple
from configparser import ConfigParser
from contextlib import contextmanager

import hglib
import pytest
import responses
from libmozdata.phabricator import PhabricatorAPI
from libmozevent.phabricator import (
    PhabricatorBuild,
    PhabricatorBuildState,
)

from code_review_bot import Level, stats
from code_review_bot.backend import BackendAPI
from code_review_bot.config import GetAppUserAgent, settings
from code_review_bot.tasks.clang_tidy import ClangTidyIssue, ClangTidyTask
from code_review_bot.tasks.default import DefaultTask

MOCK_DIR = os.path.join(os.path.dirname(__file__), "mocks")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

MockArtifactResponse = namedtuple("MockArtifactResponse", "content")


@pytest.fixture(scope="function")
def mock_repositories():
    return [
        {
            "url": "https://hg.mozilla.org/mozilla-central",
            "decision_env_prefix": "GECKO",
            "checkout": "robust",
            "try_url": "ssh://hg.mozilla.org/try",
            "try_mode": "json",
            "try_name": "try",
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
    os.environ["BULK_ISSUE_CHUNKS"] = "10"
    settings.setup(
        "test",
        ["dom/*", "tests/*.py", "test/*.c"],
        mock_repositories,
    )

    return settings


@pytest.fixture
def mock_issues(mock_task):
    """
    Build a list of dummy issues
    """
    task = mock_task(DefaultTask, "mock-analyzer")

    class MockIssue:
        def __init__(self, nb):
            self.nb = nb
            self.path = "/path/to/file"
            self.analyzer = task
            self.level = Level.Error if self.nb % 2 else Level.Warning

        def as_markdown(self):
            return f"This is the mock issue n°{self.nb}"

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
def mock_task():
    """Build configuration for any Analysis task"""

    def _build(cls, name):
        return cls(f"{name}-ID", {"task": {"metadata": {"name": name}}, "status": {}})

    return _build


@pytest.fixture
def mock_clang_tidy_issues(mock_revision, mock_task):
    """
    Build a list of clang-tidy issues
    """

    from code_review_bot import Level

    return [
        ClangTidyIssue(
            analyzer=mock_task(ClangTidyTask, "mock-clang-tidy"),
            revision=mock_revision,
            path="dom/animation/Animation.cpp",
            line=57,
            column=46,
            level=Level("error") if i % 2 else Level("warning"),
            check="clanck.checker",
            message="Some Error Message",
            publish=True,
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
        path = os.path.join(MOCK_DIR, f"phabricator_{name}.json")
        assert os.path.exists(path)
        return open(path).read()

    def diff_search(request):
        payload = dict(urllib.parse.parse_qsl(request.body))
        assert "params" in payload
        params = json.loads(payload["params"])

        name = ["diff_search"]
        for values in params.get("constraints", {}).values():
            name += values

        if os.environ.get("SPECIAL_NAME"):
            name[1] = os.environ["SPECIAL_NAME"]

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

    with open(os.path.join(os.path.join(MOCK_DIR, "phabricator_patch.diff"))) as f:
        test_patch = f.read()
    responses.add(
        responses.POST,
        "http://phabricator.test/api/differential.getrawdiff",
        body=json.dumps({"error_code": None, "error_info": None, "result": test_patch}),
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

    responses.add(
        responses.POST,
        "http://phabricator.test/api/project.search",
        body=_response("project_search"),
        content_type="application/json",
    )

    config_file = tempfile.NamedTemporaryFile()
    with open(config_file.name, "w") as f:
        custom_conf = ConfigParser()
        custom_conf.add_section("User-Agent")
        custom_conf.set("User-Agent", "name", "libmozdata")
        custom_conf.write(f)
        f.seek(0)

    from libmozdata import config

    config.set_config(config.ConfigIni(config_file.name))

    yield PhabricatorAPI(url="http://phabricator.test/api/", api_key="deadbeef")


@pytest.fixture
def mock_try_task():
    """
    Mock a remote Try task definition
    """
    return {"extra": {"code-review": {"phabricator-diff": "PHID-HMBT-test"}}}


@pytest.fixture
def mock_decision_task():
    """
    Mock a remote decision task definition
    """
    return {
        "metadata": {"name": "Mock decision task"},
        "payload": {
            "image": "taskcluster/decision",
            "env": {
                "GECKO_HEAD_REV": "deadc0ffee",
                "GECKO_BASE_REV": "c0ffeedead",
                "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                "GECKO_BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-central",
            },
        },
    }


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
                "GECKO_BASE_REV": "123deadbeef",
            }
        }
    }


@pytest.fixture
def mock_revision(mock_phabricator, mock_try_task, mock_decision_task, mock_config):
    """
    Mock a mercurial revision
    """
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        return Revision.from_try_task(mock_try_task, mock_decision_task, api)


@pytest.fixture
def mock_revision_autoland(mock_phabricator, mock_autoland_task):
    """
    Mock a mercurial revision from autoland repo
    """
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        return Revision.from_decision_task(mock_autoland_task, api)


class Response:
    "A simple response encoded as JSON"

    def __init__(self, body=None, code=200):
        self.body = body
        self.code = code

    def raise_for_status(self):
        if self.code >= 300:
            raise Exception(f"Request failed with code {self.code}")
        else:
            return json.dumps(self.body)

    @property
    def content(self):
        return self.body.encode()

    def json(self):
        return self.body


class SessionMock:
    """
    Basic mock of a request session, that returns a JSON body
    """

    # A dict mapping a method and an url to the associated response
    _callable = {}

    def reset(self):
        self._callable = {}

    def add(self, method, url, response):
        self._callable[(method, url)] = response

    def get(self, url, *args, **kwargs):
        resp_value = self._callable.get(("get", url))
        if resp_value:
            return Response(resp_value)
        else:
            return Response(None, code=404)
        if ("get", url) in self._callable:
            return Response(self._callable[("get", url)])


class MockQueue:
    """
    Mock the Taskcluster queue, by using fake tasks descriptions, relations and artifacts
    """

    def __init__(self):
        self._artifacts = {}
        self.session = SessionMock()

    def configure(self, relations):
        # Reset the session mock
        self.session.reset()

        # Create tasks
        assert isinstance(relations, dict)
        self._tasks = {
            task_id: {
                "dependencies": desc.get("dependencies", []),
                "metadata": {
                    "name": desc.get("name", f"source-test-mozlint-{task_id}")
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
        # Mock responses for each artifact
        for task_name, task in self._artifacts.items():
            for artifact in task["artifacts"]:
                url = f"http://tc.test/{task_name}/0/artifacts/{artifact['name']}"
                self.session.add("get", url, artifact["content"])

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

    def buildUrl(self, route_name, task, run, name):
        assert route_name == "getArtifact"
        return f"http://tc.test/{task}/{run}/artifacts/{name}"

    def createArtifact(self, task_id, run_id, name, payload):
        if task_id not in self._artifacts:
            self._artifacts[task_id] = {"artifacts": []}

        self._artifacts[task_id]["artifacts"].append(payload)
        return {
            "storageType": "s3",
            "putUrl": f"http://storage.test/{name}",
            "contentType": payload["contentType"],
        }


class MockIndex:
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
            raise Exception(f"Task {route} not found")
        return {"taskId": task_id}


class MockNotify:
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


@pytest.fixture(scope="function")
def mock_workflow(mock_config, mock_taskcluster_config):
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
            self.lando_api = None
            self.phabricator = None
            self.index_service = mock_taskcluster_config.get_service("index")
            self.queue_service = mock_taskcluster_config.get_service("queue")
            self.zero_coverage_enabled = True
            self.backend_api = BackendAPI()
            self.update_build = False
            self.task_failures_ignored = []
            self.clone_available = True

        def setup_mock_tasks(self, tasks):
            """
            Add mock tasks in queue & index mock services
            """
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

        assert repo != "None", "Missing repo"
        assert revision != "None", "Missing revision"

        # Check for the correct user agent
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]

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
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]
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
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]
        if revision_id in revisions:
            return (200, {}, json.dumps(revisions[revision_id]))
        return (404, {}, "")

    def post_revision(request):
        """Create a revision when not available in db"""
        payload = json.loads(request.body)
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]
        revision_id = len(revisions) + 1
        payload["id"] = revision_id
        if revision_id in revisions:
            return (400, {}, "")

        # Add backend's pre-built URLs to the output
        payload["diffs_url"] = f"http://{host}/v1/revision/{revision_id}/diffs/"
        payload["issues_bulk_url"] = f"http://{host}/v1/revision/{revision_id}/issues/"

        revisions[revision_id] = payload
        return (201, {}, json.dumps(payload))

    def get_diff(request):
        """Get a diff when available in db"""
        diff_id = int(request.path_url.split("/")[5])
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]
        if diff_id in diffs:
            return (200, {}, json.dumps(diffs[diff_id]))
        return (404, {}, "")

    def post_diff(request):
        """Create a diff when not available in db"""
        payload = json.loads(request.body)
        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]
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

        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]

        # Add a constant uuid as issue id
        payload["id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, request.url + str(len(issues[diff_id])))
        )

        issues[diff_id].append(payload)
        return (201, {}, json.dumps(payload))

    def post_issues_bulk(request):
        """Create issues in bulk on a revision"""
        payload = json.loads(request.body)

        assert GetAppUserAgent()["user-agent"] == request.headers["user-agent"]

        # Add a constant UUIDs for issues
        for index, issue in enumerate(payload["issues"]):
            issue["id"] = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL, request.url + str(index) + str(issue["hash"])
                )
            )

        issues.update({issue["id"]: issue for issue in payload["issues"]})
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
    responses.add_callback(
        responses.POST,
        re.compile(rf"^http://{host}/v1/revision/(\d+)/issues/$"),
        callback=post_issues_bulk,
    )

    return revisions, diffs, issues


class MockPhabricator:
    """
    A Mock Phabricator API server using responses
    """

    def __init__(self, base_url, auth_token):
        self.auth_token = auth_token

        # Objects storages
        self.comments = collections.defaultdict(list)
        self.inline_comments = collections.defaultdict(list)
        self.build_messages = collections.defaultdict(list)
        self.transactions = collections.defaultdict(list)

        endpoints = {
            "differential.createcomment": self.comment,
            "differential.createinline": self.comment_inline,
            "harbormaster.sendmessage": self.build_message,
            "project.search": self.search_projects,
            "differential.revision.edit": self.edit_revision,
        }

        for endpoint, callback in endpoints.items():
            responses.add_callback(
                responses.POST, f"{base_url}/api/{endpoint}", callback=callback
            )

    def parse_request(self, request, required_keys):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1

        # Check auth token
        params = json.loads(payload["params"][0])
        conduit = params.pop("__conduit__")
        assert conduit["token"] == self.auth_token

        # Check required keys
        assert set(params.keys()).issuperset(required_keys)

        return params

    def comment(self, request):
        """Post a new comment on a revision"""
        params = self.parse_request(
            request, ("revision_id", "message", "attach_inlines")
        )

        # Store the comment on the revision
        self.comments[params["revision_id"]].append(params["message"])

        # Outputs dummy empty response
        return (
            201,
            {"Content-Type": "application/json"},
            json.dumps({"error_code": None, "result": None}),
        )

    def comment_inline(self, request):
        """Post a new inline comment on a revision"""
        params = self.parse_request(
            request,
            ("diffID", "content", "filePath", "isNewFile", "lineLength", "lineNumber"),
        )

        # Store the comment on the diff
        self.inline_comments[params["diffID"]].append(params)

        # Outputs dummy empty response
        return (
            201,
            {"Content-Type": "application/json"},
            json.dumps({"error_code": None, "result": {"id": "PHID-XXXX-YYYYY"}}),
        )

    def build_message(self, request):
        """Set a new state on a Harbormaster build"""
        params = self.parse_request(request, ("receiver", "lint", "unit", "type"))

        # Store the message on the build
        self.build_messages[params["receiver"]].append(params)

        # Outputs dummy empty response
        return (
            201,
            {"Content-Type": "application/json", "unittest": "flake8-error"},
            json.dumps({"error_code": None, "result": None}),
        )

    def search_projects(self, request):
        params = self.parse_request(request, ("constraints",))

        result = None
        if params["constraints"]["slugs"] == ["taskgraph-reviewers"]:
            result = [
                {"phid": "PHID-123456789-TGReviewers", "slug": "taskgraph-reviewers"}
            ]

        return (
            201,
            {"Content-Type": "application/json"},
            json.dumps({"error_code": None, "result": {"data": result}}),
        )

    def edit_revision(self, request):
        params = self.parse_request(request, ("objectIdentifier", "transactions"))

        # Store the transactions on the revision
        self.transactions[params["objectIdentifier"]].append(params["transactions"])

        # Outputs dummy empty response
        return (
            201,
            {"Content-Type": "application/json"},
            json.dumps({"error_code": None, "result": None}),
        )


@pytest.fixture
def phab():
    return MockPhabricator("http://phabricator.test", "deadbeef")


@pytest.fixture
def sentry_event_with_colors():
    path = os.path.join(FIXTURES_DIR, "sentry_event_before.json")
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def sentry_event_without_colors():
    path = os.path.join(FIXTURES_DIR, "sentry_event_after.json")
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def mock_mercurial_repo(monkeypatch):
    """Capture hglib repository calls"""

    Commit = collections.namedtuple("Commit", "node")

    class MockRepo:
        def __init__(self):
            self.server = None
            self._calls = []

        def setcbout(self, cb):
            self._calls.append("cbout")

        def setcberr(self, cb):
            self._calls.append("cberr")

        def revert(self, path, **kwargs):
            self._calls.append(("revert", path, kwargs))

        def rawcommand(self, cmd):
            self._calls.append(("rawcommand", cmd))

        def pull(self):
            self._calls.append("pull")

        def identify(self, rev):
            self._calls.append(("identify", rev))

        def update(self, **kwargs):
            self._calls.append(("update", kwargs))

        def status(self, **kwargs):
            self._calls.append(("status", kwargs))
            return b""

        def import_(self, patches=None, **kwargs):
            self._calls.append(("import", patches.read(), kwargs))

        def add(self, path):
            self._calls.append(("add", path))

        def commit(self, **kwargs):
            self._calls.append(("commit", kwargs))

        def tip(self):
            self._calls.append("tip")
            return Commit(b"test_tip")

        def push(self, **kwargs):
            self._calls.append(("push", kwargs))

    # Provide a controlled instance on hglib.open
    mock_repo = MockRepo()
    monkeypatch.setattr(hglib, "open", lambda path: mock_repo)
    return mock_repo


class MockBuild(PhabricatorBuild):
    def __init__(self, diff_id, repo_phid, revision_id, target_phid, diff):
        config_file = tempfile.NamedTemporaryFile()
        with open(config_file.name, "w") as f:
            custom_conf = ConfigParser()
            custom_conf.add_section("User-Agent")
            custom_conf.set("User-Agent", "name", "libmozdata")
            custom_conf.write(f)
            f.seek(0)
        from libmozdata import config

        config.set_config(config.ConfigIni(config_file.name))

        self.diff_id = diff_id
        self.repo_phid = repo_phid
        self.revision_id = revision_id
        self.target_phid = target_phid
        self.diff = diff
        self.stack = []
        self.state = PhabricatorBuildState.Public
        self.revision_url = None
        self.retries = 0
