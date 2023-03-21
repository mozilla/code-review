# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot.backend import BackendAPI
from code_review_bot.tasks.clang_tidy import ClangTidyIssue


def test_publication(mock_clang_tidy_issues, mock_revision, mock_backend, mock_hgmo):
    """
    Test publication of issues on the backend
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.head_repository = "http://hgmo/test-try"
    mock_revision.base_repository = "https://hgmo/test"
    mock_revision.head_changeset = "deadbeef1234"
    mock_revision.base_changeset = "1234deadbeef"

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
        "title": "Static Analysis tests",
        "diffs_url": "http://code-review-backend.test/v1/revision/51/diffs/",
        "issues_bulk_url": "http://code-review-backend.test/v1/revision/51/issues/",
        "head_repository": "http://hgmo/test-try",
        "base_repository": "https://hgmo/test",
        "head_changeset": "deadbeef1234",
        "base_changeset": "1234deadbeef",
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
    published = r.publish_issues(mock_clang_tidy_issues, mock_revision)
    assert published == len(mock_clang_tidy_issues) == 2

    # Check the issues in the backend
    assert len(issues) == 1
    assert 42 in issues
    assert len(issues[42]) == 2
    assert issues[42] == [
        {
            "analyzer": "mock-clang-tidy",
            "check": "clanck.checker",
            "column": 46,
            "hash": "18ff7d47ce8c3a11ea19a4e2b055fd06",
            "id": "9f6aa76a-623d-5096-82ed-876b01f9fbce",
            "in_patch": False,
            "level": "warning",
            "line": 57,
            "message": "Some Error Message",
            "nb_lines": 1,
            "path": "dom/animation/Animation.cpp",
            "publishable": False,
            "validates": True,
            "fix": None,
        },
        {
            "analyzer": "mock-clang-tidy",
            "check": "clanck.checker",
            "column": 46,
            "hash": "ddf7ae1da14e80c488f99e4245e9ef79",
            "id": "98d7e3b0-e903-57e3-9973-d11d3a9849f4",
            "in_patch": False,
            "level": "error",
            "line": 57,
            "message": "Some Error Message",
            "nb_lines": 1,
            "path": "dom/animation/Animation.cpp",
            "publishable": True,
            "validates": True,
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
    mock_revision.head_repository = "http://hgmo/test-try"
    mock_revision.base_repository = "https://hgmo/test"
    mock_revision.head_changeset = "deadbeef1234"
    mock_revision.base_changeset = "1234deadbeef"

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
        "title": "Static Analysis tests",
        "diffs_url": "http://code-review-backend.test/v1/revision/51/diffs/",
        "issues_bulk_url": "http://code-review-backend.test/v1/revision/51/issues/",
        "head_repository": "http://hgmo/test-try",
        "base_repository": "https://hgmo/test",
        "head_changeset": "deadbeef1234",
        "base_changeset": "1234deadbeef",
    }


def test_repo_url(mock_revision, mock_backend, mock_hgmo):
    """
    Check that the backend client verifies repositories are URLs
    """
    r = BackendAPI()
    assert r.enabled is True

    # Invalid base repo
    mock_revision.base_repository = "test"
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Repository test is not an url"

    # Invalid head repo
    mock_revision.base_repository = "http://xxx/test"
    mock_revision.head_repository = "somewhere/test-try"
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Repository somewhere/test-try is not an url"


def test_changeset_string(mock_revision, mock_backend, mock_hgmo):
    """
    Check that the backend client verifies mercurial changesets are strings
    """
    mock_revision.head_repository = "http://hgmo/test-try"
    mock_revision.base_repository = "https://hgmo/test"

    r = BackendAPI()
    assert r.enabled is True

    # Invalid base changeset
    mock_revision.base_changeset = 4321
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Mercurial changeset must be a string"

    # Invalid head changeset
    mock_revision.base_changeset = "1234deadbeef"
    mock_revision.head_changeset = 1234
    with pytest.raises(AssertionError) as e:
        r.publish_revision(mock_revision)
    assert str(e.value) == "Mercurial changeset must be a string"


def test_publication_failures(
    mock_clang_tidy_issues, mock_revision, mock_backend, mock_hgmo
):
    """
    Test publication of issues on the backend with some bad urls
    """
    # Nothing in backend at first
    revisions, diffs, issues = mock_backend
    assert not revisions and not diffs and not issues

    # Hardcode revision & repo
    mock_revision.head_repository = "http://hgmo/test-try"
    mock_revision.base_repository = "https://hgmo/test"
    mock_revision.head_changeset = "deadbeef1234"
    mock_revision.base_changeset = "1234deadbeef"

    assert mock_revision.bugzilla_id == 1234567

    r = BackendAPI()
    assert r.enabled is True

    # Use a bad relative path in last issue
    mock_clang_tidy_issues[-1].path = "../../../bad/path.cpp"
    assert mock_clang_tidy_issues[0].path == "dom/animation/Animation.cpp"

    # Only one issue should be published as the bad one is ignored
    mock_revision.diff_issues_url = "http://code-review-backend.test/v1/diff/42/issues/"

    published = r.publish_issues(mock_clang_tidy_issues, mock_revision)
    assert published == 1

    # Check the issues in the backend
    assert len(issues) == 1
    assert 42 in issues
    assert len(issues[42]) == 1
    assert issues[42] == [
        {
            "analyzer": "mock-clang-tidy",
            "check": "clanck.checker",
            "column": 46,
            "hash": "18ff7d47ce8c3a11ea19a4e2b055fd06",
            "id": "9f6aa76a-623d-5096-82ed-876b01f9fbce",
            "in_patch": False,
            "level": "warning",
            "line": 57,
            "message": "Some Error Message",
            "nb_lines": 1,
            "path": "dom/animation/Animation.cpp",
            "publishable": False,
            "validates": True,
            "fix": None,
        }
    ]


def test_publish_issues_bulk(
    mock_clang_tidy_issues, mock_revision, mock_backend, mock_hgmo
):
    """
    Test publication of issues in bulk for a revision
    Issues missing a hash are not published
    """
    # Nothing in backend at first
    _, _, backend_issues = mock_backend
    assert not backend_issues

    # Hardcode revision & repo
    mock_revision.head_repository = "http://hgmo/test-try"
    mock_revision.base_repository = "https://hgmo/test"
    mock_revision.head_changeset = "deadbeef1234"
    mock_revision.base_changeset = "1234deadbeef"
    assert mock_revision.bugzilla_id == 1234567

    r = BackendAPI()
    assert r.enabled is True

    # Issue URL is set when publishing the issue on the backend
    mock_revision.issues_url = "http://code-review-backend.test/v1/revision/51/issues/"

    # Two issues are publishable and a third one has an erroneous path
    issues = [
        ClangTidyIssue(
            analyzer=mock_clang_tidy_issues[0].analyzer,
            revision=mock_clang_tidy_issues[0].revision,
            path="../../../an_invalid_path",
            line=42,
            column=42,
            level=mock_clang_tidy_issues[0].level,
            check="check",
            message="err",
            publish=True,
        ),
        *mock_clang_tidy_issues,
    ]

    published = r.publish_issues(issues, mock_revision, bulk=10)
    assert published == 2

    # Check the issues in the backend
    assert len(backend_issues) == 2
    assert dict(backend_issues) == {
        "852c3473-77a8-51c5-bb78-4d2d53652b0a": {
            "analyzer": "mock-clang-tidy",
            "check": "clanck.checker",
            "column": 46,
            "fix": None,
            "hash": "18ff7d47ce8c3a11ea19a4e2b055fd06",
            "id": "852c3473-77a8-51c5-bb78-4d2d53652b0a",
            "in_patch": False,
            "level": "warning",
            "line": 57,
            "message": "Some Error Message",
            "nb_lines": 1,
            "path": "dom/animation/Animation.cpp",
            "publishable": False,
            "validates": True,
        },
        "a79acfdf-522a-5063-8ce2-775b9932bd58": {
            "analyzer": "mock-clang-tidy",
            "check": "clanck.checker",
            "column": 46,
            "fix": None,
            "hash": "ddf7ae1da14e80c488f99e4245e9ef79",
            "id": "a79acfdf-522a-5063-8ce2-775b9932bd58",
            "in_patch": False,
            "level": "error",
            "line": 57,
            "message": "Some Error Message",
            "nb_lines": 1,
            "path": "dom/animation/Animation.cpp",
            "publishable": True,
            "validates": True,
        },
    }
