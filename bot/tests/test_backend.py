# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot.backend import BackendAPI


def test_publication(mock_coverity_issues, mock_revision, mock_backend, mock_hgmo):
    """
    Test publication of issues on the backend
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.repository = "http://hgmo/test-try"
    mock_revision.target_repository = "https://hgmo/test"
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
        "repository": "https://hgmo/test",
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
        "repository": "http://hgmo/test-try",
    }

    # No issues at that point
    assert len(issues) == 0

    # Let's publish them
    published = r.publish_issues(mock_coverity_issues, mock_revision)
    assert published == len(mock_coverity_issues) == 2

    # Check the issues in the backend
    assert len(issues) == 1
    assert 42 in issues
    assert len(issues[42]) == 2
    assert issues[42] == [
        {
            "analyzer": "mock-coverity",
            "check": "flag",
            "column": None,
            "hash": "3731a6559c9a72d09f4bad85db3f0416",
            "id": "9f6aa76a-623d-5096-82ed-876b01f9fbce",
            "in_patch": False,
            "level": "warning",
            "line": None,
            "message": "Unidentified symbol",
            "nb_lines": 1,
            "path": "some/file/path",
            "publishable": False,
            "validates": False,
            "fix": None,
        },
        {
            "analyzer": "mock-coverity",
            "check": "flag",
            "column": None,
            "hash": "1fcc4d02d6184028f40b48e877be62b4",
            "id": "98d7e3b0-e903-57e3-9973-d11d3a9849f4",
            "in_patch": False,
            "level": "warning",
            "line": 1,
            "message": "Unidentified symbol",
            "nb_lines": 1,
            "path": "some/file/path",
            "publishable": False,
            "validates": False,
            "fix": None,
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
    mock_revision.repository = "http://hgmo/test-try"
    mock_revision.target_repository = "https://hgmo/test"
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
        "repository": "https://hgmo/test",
        "title": "Static Analysis tests",
        "diffs_url": "http://code-review-backend.test/v1/revision/51/diffs/",
    }


def test_repo_url(mock_coverity_issues, mock_revision, mock_backend, mock_hgmo):
    """
    Check that the backend client verifies repositories are URLs
    """
    mock_revision.mercurial_revision = "deadbeef1234"

    r = BackendAPI()
    assert r.enabled is True

    # Invalid target repo
    mock_revision.target_repository = "test"
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Repository test is not an url"

    # Invalid repo
    mock_revision.target_repository = "http://xxx/test"
    mock_revision.repository = "somewhere/test-try"
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Repository somewhere/test-try is not an url"


def test_publication_failures(
    mock_coverity_issues, mock_revision, mock_backend, mock_hgmo
):
    """
    Test publication of issues on the backend with some bad urls
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.repository = "http://hgmo/test-try"
    mock_revision.target_repository = "https://hgmo/test"
    mock_revision.mercurial_revision = "deadbeef1234"

    assert mock_revision.bugzilla_id == 1234567

    r = BackendAPI()
    assert r.enabled is True

    # Use a bad relative path in last issue
    mock_coverity_issues[-1].path = "../../../bad/path.cpp"
    assert mock_coverity_issues[0].path == "some/file/path"

    # Only one issue should be published as the bad one is ignored
    mock_revision.issues_url = "http://code-review-backend.test/v1/diff/42/issues/"
    published = r.publish_issues(mock_coverity_issues, mock_revision)
    assert published == 1

    # Check the issues in the backend
    assert len(issues) == 1
    assert 42 in issues
    assert len(issues[42]) == 1
    assert issues[42] == [
        {
            "analyzer": "mock-coverity",
            "check": "flag",
            "column": None,
            "hash": "3731a6559c9a72d09f4bad85db3f0416",
            "id": "9f6aa76a-623d-5096-82ed-876b01f9fbce",
            "in_patch": False,
            "level": "warning",
            "line": None,
            "message": "Unidentified symbol",
            "nb_lines": 1,
            "path": "some/file/path",
            "publishable": False,
            "validates": False,
            "fix": None,
        }
    ]
