# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import responses

from code_review_bot.config import settings
from code_review_bot.revisions import ImprovementPatch
from code_review_bot.tasks.default import DefaultTask


def test_publication(
    monkeypatch, mock_taskcluster_config, mock_repositories, mock_task
):
    """
    Check a patch publication through Taskcluster services
    """

    # Setup local config as running in a real Taskcluster task with proxy
    monkeypatch.setenv("TASK_ID", "fakeTaskId")
    monkeypatch.setenv("RUN_ID", "0")
    monkeypatch.setenv("TASKCLUSTER_PROXY_URL", "http://proxy")
    settings.setup("test", [], mock_repositories)

    # Mock the storage response
    responses.add(
        responses.PUT,
        "http://storage.test/public/patch/mock-analyzer-test-improvement.diff",
        json={},
        headers={"ETag": "test123"},
    )

    patch = ImprovementPatch(
        mock_task(DefaultTask, "mock-analyzer"), "test-improvement", "This is good code"
    )
    assert patch.url is None

    patch.publish()
    assert (
        patch.url
        == "https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/fakeTaskId/runs/0/artifacts/public/patch/mock-analyzer-test-improvement.diff"
    )

    # Check the mock has been called
    assert [c.request.url for c in responses.calls] == [
        "http://storage.test/public/patch/mock-analyzer-test-improvement.diff"
    ]
