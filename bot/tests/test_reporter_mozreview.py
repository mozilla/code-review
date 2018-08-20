# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest


def test_conf(mock_mozreview):
    '''
    Test mozreview reporter configuration
    '''
    from static_analysis_bot.report.mozreview import MozReviewReporter

    # Missing emails conf
    with pytest.raises(AssertionError):
        MozReviewReporter({}, 'test_tc', 'token_tc')

    # Valid auth
    conf = {
        'username': 'devbot',
        'api_key': 'deadbeef123',
        'url': 'http://mozreview.test',
    }
    r = MozReviewReporter(conf, 'test_tc', 'token_tc')
    assert r.api is not None


def test_review_publication(mock_mozreview, mock_issues, mock_phabricator):
    '''
    Test publication of a single review
    '''
    from static_analysis_bot.report.mozreview import MozReviewReporter
    from static_analysis_bot.revisions import MozReviewRevision

    # Publish issues on mozreview
    conf = {
        'username': 'devbot',
        'api_key': 'deadbeef123',
        'url': 'http://mozreview.test',
    }
    r = MozReviewReporter(conf, 'test_tc', 'token_tc')
    mrev = MozReviewRevision('12345', 'abcdef', '1')
    out = r.publish(mock_issues, mrev)
    assert out is None  # no publication (no clang-tidy)


def test_review_api(mock_mozreview):
    '''
    Test low level mozreview api
    '''
    from static_analysis_bot.report.mozreview import MozReviewReporter, MozReview

    # Publish issues on mozreview
    conf = {
        'username': 'devbot',
        'api_key': 'deadbeef123',
        'url': 'http://mozreview.test',
    }
    reporter = MozReviewReporter(conf, 'test_tc', 'token_tc')
    review = MozReview(reporter.api, 12345, 2)
    assert review.user['id'] == 42

    # Test we only have our own comments (no anotherUser)
    assert len(review.existing_comments) == 2
    assert review.existing_comments == [
        {
            'filediff_id': 31,
            'first_line': 12,
            'issue_opened': False,
            'num_lines': 3,
            'text': 'Error: Dummy test error [linter]',
        },
        {
            'filediff_id': 31,
            'first_line': 29,
            'issue_opened': False,
            'num_lines': 3,
            'text': 'Error: another complex test error [linter]',
        }
    ]

    # No comments at first
    assert len(review.comments) == 0

    # Add a new comment
    review.comment(
        'test.cpp',
        2,
        1,
        'Error: a new issue detected [linter]',
    )
    assert len(review.comments) == 1

    # Add an existing comment
    # It should be skipped
    review.comment(
        'test.cpp',
        12,
        3,
        'Error: Dummy test error [linter]',
        issue_opened=False,
    )
    assert len(review.comments) == 1


def test_comment(mock_mozreview, test_cpp, mock_revision):
    '''
    Test comment creation for specific issues
    '''
    from static_analysis_bot.clang.tidy import ClangTidyIssue
    from static_analysis_bot.clang.format import ClangFormatIssue
    from static_analysis_bot.lint import MozLintIssue
    from static_analysis_bot.report.base import Reporter

    # Init dummy reporter
    class TestReporter(Reporter):
        def __init__(self):
            pass
    reporter = TestReporter()

    # Build clang tidy fake issue, while forcing publication status
    header = ('test.cpp', 1, 1, 'error', 'Dummy message', 'test-check')
    clang_tidy_publishable = ClangTidyIssue(header, mock_revision)
    clang_tidy_publishable.is_publishable = lambda: True
    assert clang_tidy_publishable.is_publishable()
    issues = [clang_tidy_publishable, ]

    assert reporter.build_comment(issues, 'https://report.example.com') == '''
Code analysis found 1 defect in this patch:
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check path/to/file.cpp` (C/C++)


If you see a problem in this automated review, please report it here: https://report.example.com
'''

    # Now add a clang-format issue
    clang_format_publishable = ClangFormatIssue('test.cpp', '', '', ('delete', 1, 2, 3, 4), mock_revision)
    clang_format_publishable.is_publishable = lambda: True
    assert clang_tidy_publishable.is_publishable()
    issues.append(clang_format_publishable)

    assert reporter.build_comment(issues, 'https://report.example.com') == '''
Code analysis found 2 defects in this patch:
 - 1 defect found by clang-format
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach clang-format -p path/to/file.cpp` (C/C++)
 - `./mach static-analysis check path/to/file.cpp` (C/C++)


If you see a problem in this automated review, please report it here: https://report.example.com
'''

    # Now add a mozlint issue
    mozlint_publishable = MozLintIssue('test.cpp', 1, 'error', 1, 'test', 'Dummy test', 'dummy rule', mock_revision)
    mozlint_publishable.is_publishable = lambda: True
    assert mozlint_publishable.is_publishable()
    issues.append(mozlint_publishable)

    assert reporter.build_comment(issues, 'https://report.example.com') == '''
Code analysis found 3 defects in this patch:
 - 1 defect found by clang-format
 - 1 defect found by clang-tidy
 - 1 defect found by mozlint

You can run this analysis locally with:
 - `./mach clang-format -p path/to/file.cpp` (C/C++)
 - `./mach static-analysis check path/to/file.cpp` (C/C++)
 - `./mach lint path/to/file` (JS/Python/etc)


If you see a problem in this automated review, please report it here: https://report.example.com
'''
