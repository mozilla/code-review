# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.backend import BackendAPI


def test_publication(mock_coverity_issues, mock_revision, mock_backend, mock_hgmo):
    """
    Test publication of issues on the backend
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.repository = "test-try"
    mock_revision.target_repository = "test"
    mock_revision.mercurial_revision = "deadbeef1234"

    assert mock_revision.bugzilla_id == 1234567

    r = BackendAPI()
    assert r.enabled is True
    r.publish_revision(mock_revision)

    # Check the revision in the backend
    assert len(revisions) == 1
    assert 51 in revisions
    assert revisions[51] == {
        "bugzilla_id": 1234567,
        "id": 51,
        "phid": "PHID-DREV-zzzzz",
        "repository": "test",
        "title": "Static Analysis tests",
        "diffs_url": "http://code-review-backend.test/v1/revision/51/diffs/",
    }

    # Check the diff in the backend
    assert len(diffs) == 1
    assert 42 in diffs
    assert diffs[42] == {
        "id": 42,
        "issues_url": "http://code-review-backend.test/v1/diff/42/issues/",
        "mercurial_hash": "deadbeef1234",
        "phid": "PHID-DIFF-test",
        "review_task_id": "local instance",
        "analyzers_group_id": "remoteTryGroup",
    }

    # No issues at that point
    assert len(issues) == 0

    # Let's publish them
    r.publish_issues(mock_coverity_issues, mock_revision)

    # Check the issues in the backend
    assert len(issues) == 1
    assert 42 in issues
    assert len(issues[42]) == 2
    assert issues[42] == [
        {
            "analyzer": "mock-coverity",
            "check": "flag",
            "column": None,
            "hash": "783cb790ac376965c0df0f6be17545df",
            "id": "9f6aa76a-623d-5096-82ed-876b01f9fbce",
            "in_patch": False,
            "is_new": False,
            "level": "error",
            "line": 0,
            "message": "Unidentified symbol",
            "nb_lines": 1,
            "path": "some/file/path",
            "publishable": False,
            "validates": False,
        },
        {
            "analyzer": "mock-coverity",
            "check": "flag",
            "column": None,
            "hash": "172f015fbc43268d712c2fc7acbf1023",
            "id": "98d7e3b0-e903-57e3-9973-d11d3a9849f4",
            "in_patch": False,
            "is_new": False,
            "level": "error",
            "line": 1,
            "message": "Unidentified symbol",
            "nb_lines": 1,
            "path": "some/file/path",
            "publishable": False,
            "validates": False,
        },
    ]


def test_missing_bugzilla_id(mock_revision, mock_backend, mock_hgmo):
    """
    Test revision creation on the backend without a bugzilla id (None instead)
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.repository = "test-try"
    mock_revision.target_repository = "test"
    mock_revision.mercurial_revision = "deadbeef1234"

    # Set bugzilla id as empty string
    mock_revision.revision["fields"]["bugzilla.bug-id"] = ""
    assert mock_revision.bugzilla_id is None

    r = BackendAPI()
    r.publish_revision(mock_revision)

    assert len(revisions) == 1
    assert 51 in revisions
    assert revisions[51] == {
        "bugzilla_id": None,
        "id": 51,
        "phid": "PHID-DREV-zzzzz",
        "repository": "test",
        "title": "Static Analysis tests",
        "diffs_url": "http://code-review-backend.test/v1/revision/51/diffs/",
    }
