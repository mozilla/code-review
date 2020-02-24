# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import responses

from code_review_bot.revisions import Revision

MOZILLA_CENTRAL_DECISION_TASK = {
    "metadata": {"name": "Fake decision task"},
    "payload": {
        "env": {
            "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
            "GECKO_BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-central",
            "GECKO_HEAD_REV": "abcdef12",
            "GECKO_BASE_REV": "aaaaaaaa",
        }
    },
}


def test_task_structure():
    # No data
    with pytest.raises(KeyError) as e:
        Revision.from_try({}, None)
    assert str(e.value) == "'metadata'"

    # No payload
    decision_task = {
        "metadata": {"name": "Fake decision task"},
        "payload": {"env": {"KEY": "VALUE"}},
    }
    with pytest.raises(AssertionError) as e:
        Revision.from_try(decision_task, None)
    assert str(e.value) == "Unsupported decision task"


def test_mozila_central(mock_config, mock_phabricator, mock_hgmo):
    """
    Simple test case using mock config & hgmo
    """

    with mock_phabricator as phab:
        revision = Revision.from_try(MOZILLA_CENTRAL_DECISION_TASK, phab)

    assert revision.as_dict() == {
        "bugzilla_id": 1234567,
        "diff_id": 42,
        "diff_phid": "PHID-DIFF-test",
        "has_clang_files": False,
        "id": 51,
        "mercurial_revision": "abcdef12",
        "phid": "PHID-DREV-zzzzz",
        "repository": "https://hg.mozilla.org/try",
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "url": "https://phabricator.test/D51",
    }


@pytest.mark.parametrize(
    "try_task_config, result, message",
    [
        ({}, Exception, "Invalid try task config version"),
        ({"version": 1}, Exception, "Invalid try task config version"),
        ({"version": "something"}, Exception, "Invalid try task config version"),
        ({"version": 2}, Exception, "Missing parameters"),
        (
            {"version": 2, "parameters": {}},
            Exception,
            "Unsupported try_task_config json payload",
        ),
        (
            {"version": 2, "parameters": {"SomeOtherKey": "XXX"}},
            Exception,
            "Unsupported try_task_config json payload",
        ),
        (
            {"version": 2, "parameters": {"phabricator_diff": "XXX"}},
            Exception,
            "Not a Phabricator build phid",
        ),
        (
            {
                "version": 2,
                "parameters": {"code-review": {"phabricator-build-target": "XXX"}},
            },
            Exception,
            "Not a Phabricator build phid",
        ),
        ({"version": 2, "parameters": {"phabricator_diff": "PHID-HMBT-123"}}, True, ""),
        (
            {
                "version": 2,
                "parameters": {
                    "code-review": {"phabricator-build-target": "PHID-HMBT-123"}
                },
            },
            True,
            "",
        ),
    ],
)
def test_try_task_config(
    try_task_config, result, message, mock_phabricator, mock_config
):
    """Test different try_task_config payloads"""

    responses.add(
        responses.GET,
        "https://hg.mozilla.org/try/raw-file/abcdef12/try_task_config.json",
        content_type="application/json",
        body=json.dumps(try_task_config),
    )

    if result is not True:
        # Check exceptions
        with pytest.raises(result) as e:
            with mock_phabricator as phab:
                revision = Revision.from_try(MOZILLA_CENTRAL_DECISION_TASK, phab)
        assert str(e.value) == message

    else:
        # Check working flow
        with mock_phabricator as phab:
            revision = Revision.from_try(MOZILLA_CENTRAL_DECISION_TASK, phab)

        assert revision.mercurial_revision == "abcdef12"
        assert revision.repository == "https://hg.mozilla.org/try"
        assert revision.target_repository == "https://hg.mozilla.org/mozilla-central"
        assert revision.build_target_phid == "PHID-HMBT-123"


@pytest.mark.parametrize(
    "env, mercurial_revision, repository",
    [
        (
            {
                "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                "GECKO_BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-unified",
                "GECKO_HEAD_REV": "abcdef12",
                "GECKO_BASE_REV": "aaaaaaaa",
            },
            "abcdef12",
            "https://hg.mozilla.org/try",
        ),
        (
            {
                "TASKGRAPH_HEAD_REPO": "https://hg.mozilla.org/ci/taskgraph-try",
                "TASKGRAPH_BASE_REPO": "https://hg.mozilla.org/ci/taskgraph",
                "TASKGRAPH_HEAD_REV": "123456789",
            },
            "123456789",
            "https://hg.mozilla.org/ci/taskgraph-try",
        ),
    ],
)
def test_building_revision(
    env, mercurial_revision, repository, mock_phabricator, mock_config
):
    """Test different decision tasks payload"""
    responses.add(
        responses.GET,
        f"{repository}/raw-file/{mercurial_revision}/try_task_config.json",
        content_type="application/json",
        body=json.dumps(
            {
                "version": 2,
                "parameters": {
                    "code-review": {"phabricator-build-target": "PHID-HMBT-fakeBuild"}
                },
            }
        ),
    )

    decision_task = {
        "metadata": {"name": "Fake decision task"},
        "payload": {"env": env},
    }

    assert len(mock_config.repositories) == 3

    with mock_phabricator as phab:
        revision = Revision.from_try(decision_task, phab)

    assert revision.mercurial_revision == mercurial_revision
    assert revision.repository == repository
    assert revision.build_target_phid == "PHID-HMBT-fakeBuild"
