# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os.path
import urllib.parse
from contextlib import contextmanager

import pytest
import responses
from libmozevent.phabricator import PhabricatorActions

from code_review_events import community_taskcluster_config, taskcluster_config

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
@contextmanager
def PhabricatorMock():
    """
    Mock phabricator authentication process
    """
    json_headers = {"Content-Type": "application/json"}

    def _response(name):
        path = os.path.join(FIXTURES_DIR, "phabricator", f"{name}.json")
        assert os.path.exists(path), f"Missing mock {path}"
        return open(path).read()

    def _phab_params(request):
        # What a weird way to send parameters
        return json.loads(urllib.parse.parse_qs(request.body)["params"][0])

    def _diff_search(request):
        params = _phab_params(request)
        assert "constraints" in params
        if "revisionPHIDs" in params["constraints"]:
            # Search from revision
            mock_name = "search-{}".format(params["constraints"]["revisionPHIDs"][0])
        elif "phids" in params["constraints"]:
            # Search from diffs
            diffs = "-".join(params["constraints"]["phids"])
            mock_name = f"search-{diffs}"
        elif "ids" in params["constraints"]:
            assert len(params["constraints"]["ids"]) == 1
            mock_name = "search-{}".format(params["constraints"]["ids"][0])
        else:
            raise Exception(f"Unsupported diff mock {params}")
        return (200, json_headers, _response(mock_name))

    def _diff_raw(request):
        params = _phab_params(request)
        assert "diffID" in params
        return (200, json_headers, _response("raw-{}".format(params["diffID"])))

    def _edges(request):
        params = _phab_params(request)
        assert "sourcePHIDs" in params
        return (
            200,
            json_headers,
            _response("edges-{}".format(params["sourcePHIDs"][0])),
        )

    def _create_artifact(request):
        params = _phab_params(request)
        assert "buildTargetPHID" in params
        return (
            200,
            json_headers,
            _response("artifact-{}".format(params["buildTargetPHID"])),
        )

    def _send_message(request):
        params = _phab_params(request)
        assert "receiver" in params
        name = "message-{}-{}".format(params["receiver"], params["type"])
        if params["unit"]:
            name += "-unit"
        if params["lint"]:
            name += "-lint"
        return (200, json_headers, _response(name))

    def _project_search(request):
        params = _phab_params(request)
        assert "constraints" in params
        assert "slugs" in params["constraints"]
        return (200, json_headers, _response("projects"))

    def _revision_search(request):
        params = _phab_params(request)
        assert "constraints" in params
        assert "ids" in params["constraints"]
        assert "attachments" in params
        assert "projects" in params["attachments"]
        assert "reviewers" in params["attachments"]
        assert params["attachments"]["projects"]
        assert params["attachments"]["reviewers"]
        mock_name = "revision-search-{}".format(params["constraints"]["ids"][0])
        return (200, json_headers, _response(mock_name))

    def _user_search(request):
        params = _phab_params(request)
        assert "constraints" in params
        if "phids" in params["constraints"]:
            mock_name = "user-search-{}".format(params["constraints"]["phids"][0])
        elif "usernames" in params["constraints"]:
            mock_name = "user-search-{}".format(
                "-".join(sorted(params["constraints"]["usernames"]))
            )
        else:
            raise Exception("Unsupported user search")

        return (200, json_headers, _response(mock_name))

    with responses.RequestsMock(assert_all_requests_are_fired=False) as resp:
        resp.add(
            responses.POST,
            "http://phabricator.test/api/user.whoami",
            body=_response("auth"),
            content_type="application/json",
        )

        resp.add_callback(
            responses.POST, "http://phabricator.test/api/edge.search", callback=_edges
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/differential.diff.search",
            callback=_diff_search,
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/differential.getrawdiff",
            callback=_diff_raw,
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/harbormaster.createartifact",
            callback=_create_artifact,
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/harbormaster.sendmessage",
            callback=_send_message,
        )

        resp.add(
            responses.POST,
            "http://phabricator.test/api/diffusion.repository.search",
            body=_response("repositories"),
            content_type="application/json",
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/project.search",
            callback=_project_search,
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/differential.revision.search",
            callback=_revision_search,
        )

        resp.add_callback(
            responses.POST,
            "http://phabricator.test/api/user.search",
            callback=_user_search,
        )

        actions = PhabricatorActions(
            url="http://phabricator.test/api/", api_key="deadbeef"
        )
        actions.mocks = resp  # used to assert in tests on callbacks
        yield actions


@pytest.fixture
def mock_taskcluster():
    """
    Mock Taskcluster authentication
    """
    taskcluster_config.options = {"rootUrl": "http://taskcluster.test"}
    community_taskcluster_config.options = {
        "rootUrl": "http://community_taskcluster.test"
    }

    def _response(name):
        path = os.path.join(FIXTURES_DIR, "taskcluster", name)
        assert os.path.exists(path), f"Missing mock {path}"
        return open(path).read()

    responses.add(
        responses.GET,
        "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task-group/aGroup/list",
        json={"taskGroupId": "aGroup", "tasks": []},
    )

    return _response


@pytest.fixture
def mock_treeherder():
    def _response(name):
        path = os.path.join(FIXTURES_DIR, "treeherder", name)
        assert os.path.exists(path), f"Missing mock {path}"
        return open(path).read()

    return _response
