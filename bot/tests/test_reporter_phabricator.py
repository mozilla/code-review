# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import urllib

import responses

VALID_CLANG_TIDY_MESSAGE = '''
Code analysis found 1 defect in this patch:
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check path/to/file.cpp` (C/C++)

If you see a problem in this automated review, please report it here: https://bit.ly/2IyNRy2
'''

VALID_CLANG_FORMAT_MESSAGE = '''
Code analysis found 1 defect in this patch:
 - 1 defect found by clang-format

You can run this analysis locally with:
 - `./mach clang-format -p path/to/file.cpp` (C/C++)

For your convenience, here is a patch that fixes all the clang-format defects: https://diff.url (use it in your repository with `hg import` or `git apply`)

If you see a problem in this automated review, please report it here: https://bit.ly/2IyNRy2
'''


@responses.activate
def test_phabricator_clang_tidy(mock_repository, mock_phabricator):
    '''
    Test Phabricator reporter publication on a mock clang-tidy issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import PhabricatorRevision
    from static_analysis_bot.clang.tidy import ClangTidyIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details == {
            'revision_id': 51,
            'message': VALID_CLANG_TIDY_MESSAGE,
            'attach_inlines': 1,
            '__conduit__': {'token': 'deadbeef'},
        }

        # Outputs dummy empty response
        resp = {
            'error_code': None,
            'result': None,
        }
        return 201, {'Content-Type': 'application/json', 'unittest': 'clang-tidy'}, json.dumps(resp)

    responses.add_callback(
        responses.POST,
        'http://phabricator.test/api/differential.createcomment',
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = PhabricatorRevision('PHID-DIFF-abcdef', api)
        revision.lines = {
            # Add dummy lines diff
            'test.cpp': [41, 42, 43],
        }
        reporter = PhabricatorReporter(api=api)

    issue_parts = ('test.cpp', '42', '51', 'error', 'dummy message', 'modernize-use-nullptr')
    issue = ClangTidyIssue(issue_parts, revision)
    assert issue.is_publishable()

    reporter.publish([issue, ], revision)

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'clang-tidy'


@responses.activate
def test_phabricator_clang_format(mock_repository, mock_phabricator):
    '''
    Test Phabricator reporter publication on a mock clang-format issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import PhabricatorRevision
    from static_analysis_bot.clang.format import ClangFormatIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details['message'] == VALID_CLANG_FORMAT_MESSAGE

        # Outputs dummy empty response
        resp = {
            'error_code': None,
            'result': None,
        }
        return 201, {'Content-Type': 'application/json', 'unittest': 'clang-format'}, json.dumps(resp)

    responses.add_callback(
        responses.POST,
        'http://phabricator.test/api/differential.createcomment',
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = PhabricatorRevision('PHID-DIFF-abcdef', api)
        revision.lines = {
            # Add dummy lines diff
            'test.cpp': [41, 42, 43],
        }
        reporter = PhabricatorReporter(api=api)

    issue = ClangFormatIssue('test.cpp', 42, 1, revision)
    assert issue.is_publishable()

    revision.improvement_patches = {
        'clang-format': 'https://diff.url'
    }

    reporter.publish([issue, ], revision)

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'clang-format'
