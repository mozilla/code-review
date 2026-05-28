# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import json
from pathlib import Path
from textwrap import dedent

import responses
from conftest import FIXTURES_DIR

from code_review_bot.report.github import GithubReporter
from code_review_bot.revisions import GithubRevision, Revision
from code_review_bot.tasks.clang_tidy import ClangTidyIssue, ClangTidyTask
from code_review_bot.tasks.coverage import CoverageIssue, ZeroCoverageTask


def test_github_review(
    monkeypatch,
    mock_github,
    mock_config,
    phab,
    mock_try_task,
    mock_github_decision_task,
    mock_task,
    mock_backend_secret,
):
    """
    Report 2 clang tidy issues by pushing a review to a Github pull request
    """
    revision = Revision.from_try_task(mock_try_task, mock_github_decision_task, None)
    assert isinstance(revision, GithubRevision)
    revision.lines = {
        # Add dummy lines diff
        "test.txt": [0],
        "path/to/test.cpp": [0],
        "another_test.cpp": [41, 42, 43],
    }
    revision.files = ["test.txt", "test.cpp", "another_test.cpp"]
    revision.id = 52
    monkeypatch.setattr(revision, "load_file", lambda x: "some_content")

    reporter = GithubReporter(
        {
            "client_id": "client_id",
            "private_key_pem": (Path(FIXTURES_DIR) / "private_key.pem").read_text(),
            "installation_id": 123456789,
        }
    )

    issue_clang_tidy = ClangTidyIssue(
        mock_task(ClangTidyTask, "source-test-clang-tidy"),
        revision,
        "another_test.cpp",
        "42",
        "51",
        "modernize-use-nullptr",
        "dummy message",
    )
    assert issue_clang_tidy.in_patch is True
    assert issue_clang_tidy.is_publishable()

    issue_coverage = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "path/to/test.cpp",
        "1",
        "This file is uncovered",
        revision,
    )
    assert issue_coverage.in_patch is False
    assert issue_coverage.is_publishable()

    # Mock to publish a comment, regarding issues outside of the patch
    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        json={},
    )

    # Mock to publish a new review
    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews",
        json={},
    )

    # Mock to list existing reviews
    responses.add(
        responses.GET,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews",
        json=[],
    )

    reporter.publish([issue_clang_tidy, issue_coverage], revision, [], [], [])
    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("GET", "https://github.com/owner/repo-name/pull/1.diff"),
        ("GET", "https://api.github.com:443/app/installations"),
        (
            "POST",
            "https://api.github.com:443/app/installations/123456789/access_tokens",
        ),
        ("GET", "https://api.github.com:443/repos/owner/repo-name"),
        ("GET", "https://api.github.com:443/repos/owner/repo-name/pulls/1"),
        (
            "GET",
            "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews",
        ),
        ("POST", "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments"),
        (
            "GET",
            "https://api.github.com:443/repos/owner/repo-name",
        ),
        (
            "GET",
            "https://api.github.com:443/repos/owner/repo-name/pulls/1",
        ),
        (
            "GET",
            "https://api.github.com:443/repos/owner/repo-name/commits/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        ("POST", "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews"),
    ]
    comment_body = next(
        call.request.body
        for call in responses.calls
        if (call.request.method, call.request.url)
        == ("POST", "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments")
    )
    assert json.loads(comment_body) == {
        "body": dedent("""
            Code review bot detected 1 issues outside of the patch:
            * `path/to/test.cpp:1` This file is uncovered
        """).strip()
    }

    review_creation = responses.calls[-1]
    assert json.loads(review_creation.request.body) == {
        "body": "2 issues have been found in this revision",
        "comments": [
            {
                "body": "dummy message",
                "path": "another_test.cpp",
                "line": 42,
            },
        ],
        "commit_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "event": "REQUEST_CHANGES",
    }


def test_github_review_cleanup(
    monkeypatch,
    mock_github,
    mock_config,
    phab,
    mock_try_task,
    mock_github_decision_task,
    mock_task,
    mock_backend_secret,
):
    """In case no issue is found, previous reviews are dismissed"""
    revision = Revision.from_try_task(mock_try_task, mock_github_decision_task, None)
    revision.lines = {}
    revision.files = ["test.txt", "test.cpp", "another_test.cpp"]
    revision.id = 52
    reporter = GithubReporter(
        {
            "client_id": "client_id",
            "private_key_pem": (Path(FIXTURES_DIR) / "private_key.pem").read_text(),
            "installation_id": 123456789,
        }
    )

    responses.add(
        responses.GET,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews",
        json=[
            {"id": 1, "user": {"login": "a-moz-developer"}},
            {
                "id": 2,
                "user": {"login": "mozilla-code-review[bot]"},
                "pull_request_url": "https://api.github.com/repos/owner/repo-name/pulls/2",
            },
        ],
    )

    responses.add(
        responses.PUT,
        "https://api.github.com:443/repos/owner/repo-name/pulls/2/reviews/2/dismissals",
        json={},
    )

    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        json={},
    )

    reporter.publish([], revision, [], [], [])
    assert [(call.request.method, call.request.url) for call in responses.calls] == [
        ("GET", "https://github.com/owner/repo-name/pull/1.diff"),
        ("GET", "https://api.github.com:443/app/installations"),
        (
            "POST",
            "https://api.github.com:443/app/installations/123456789/access_tokens",
        ),
        ("GET", "https://api.github.com:443/repos/owner/repo-name"),
        ("GET", "https://api.github.com:443/repos/owner/repo-name/pulls/1"),
        ("GET", "https://api.github.com:443/repos/owner/repo-name/pulls/1/reviews"),
        (
            "PUT",
            "https://api.github.com:443/repos/owner/repo-name/pulls/2/reviews/2/dismissals",
        ),
        (
            "POST",
            "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        ),
    ]

    # Check published comment
    assert json.loads(responses.calls[-1].request.body) == {
        "body": "Previous issues have been fixed. This pull request is :ok:"
    }
