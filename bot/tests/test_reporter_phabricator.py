# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import unittest
import urllib

import pytest
import responses

VALID_CLANG_TIDY_MESSAGE = '''
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check another_test.cpp` (C/C++)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
'''  # noqa

VALID_CLANG_FORMAT_MESSAGE = '''
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-format

You can run this analysis locally with:
 - `./mach clang-format -s -p dom/test.cpp` (C/C++)

For your convenience, [here is a patch]({results}/clang-format-PHID-DIFF-test.diff) that fixes all the clang-format defects (use it in your repository with `hg import` or `git apply -p0`).

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
'''  # noqa


VALID_COVERAGE_MESSAGE = '''
In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
test.cpp

Should they have tests, or are they dead code?
You can file a bug blocking https://bugzilla.mozilla.org/show_bug.cgi?id=1415824 for untested files that should be tested.
You can file a bug blocking https://bugzilla.mozilla.org/show_bug.cgi?id=1415819 for untested files that should be removed.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
'''  # noqa


@responses.activate
def test_phabricator_clang_tidy(mock_phabricator, mock_try_task):
    '''
    Test Phabricator reporter publication on a mock clang-tidy issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision
    from static_analysis_bot.tasks.clang_tidy import ClangTidyIssue

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
        revision = Revision(api, mock_try_task)
        revision.lines = {
            # Add dummy lines diff
            'another_test.cpp': [41, 42, 43],
        }
        revision.files = ['another_test.cpp']
        reporter = PhabricatorReporter({'analyzers': ['clang-tidy'], 'modes': ('comment')}, api=api)

    issue = ClangTidyIssue(revision, 'another_test.cpp', '42', '51', 'modernize-use-nullptr', 'dummy message', 'error')
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue, ], revision)
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'clang-tidy'


@responses.activate
def test_phabricator_clang_format(mock_config, mock_phabricator, mock_try_task):
    '''
    Test Phabricator reporter publication on a mock clang-format issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision, ImprovementPatch
    from static_analysis_bot.tasks.clang_format import ClangFormatIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details['message'] == VALID_CLANG_FORMAT_MESSAGE.format(results=mock_config.taskcluster.results_dir)

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
        revision = Revision(api, mock_try_task)
        revision.lines = {
            # Add dummy lines diff
            'test.cpp': [41, 42, 43],
            'dom/test.cpp': [42, ],
        }
        reporter = PhabricatorReporter({'analyzers': ['clang-format']}, api=api)

    issue = ClangFormatIssue('dom/test.cpp', 42, 1, revision)
    assert issue.is_publishable()

    revision.improvement_patches = [
        ImprovementPatch('clang-format', repr(revision), 'Some lint fixes'),
    ]
    list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

    issues, patches = reporter.publish([issue, ], revision)
    assert len(issues) == 1
    assert len(patches) == 1

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'clang-format'


@responses.activate
def test_phabricator_coverage(mock_config, mock_phabricator, mock_try_task):
    '''
    Test Phabricator reporter publication on a mock coverage issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision
    from static_analysis_bot.tasks.coverage import CoverageIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details['message'] == VALID_COVERAGE_MESSAGE.format(results=mock_config.taskcluster.results_dir)

        # Outputs dummy empty response
        resp = {
            'error_code': None,
            'result': None,
        }
        return 201, {'Content-Type': 'application/json', 'unittest': 'coverage'}, json.dumps(resp)

    responses.add_callback(
        responses.POST,
        'http://phabricator.test/api/differential.createcomment',
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision(api, mock_try_task)
        revision.lines = {
            # Add dummy lines diff
            'test.txt': [0],
            'test.cpp': [0],
            'dom/test.cpp': [42, ],
        }
        reporter = PhabricatorReporter({'analyzers': ['coverage']}, api=api)

    issue = CoverageIssue('test.cpp', 0, 'This file is uncovered', revision)
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue, ], revision)
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'coverage'


@responses.activate
def test_phabricator_clang_tidy_and_coverage(mock_config, mock_phabricator, mock_try_task):
    '''
    Test Phabricator reporter publication on a mock coverage issue
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision
    from static_analysis_bot.tasks.coverage import CoverageIssue
    from static_analysis_bot.tasks.clang_tidy import ClangTidyIssue

    def _check_comment_sa(request):
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

    def _check_comment_ccov(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details['message'] == VALID_COVERAGE_MESSAGE.format(results=mock_config.taskcluster.results_dir)

        # Outputs dummy empty response
        resp = {
            'error_code': None,
            'result': None,
        }
        return 201, {'Content-Type': 'application/json', 'unittest': 'coverage'}, json.dumps(resp)

    responses.add_callback(
        responses.POST,
        'http://phabricator.test/api/differential.createcomment',
        callback=_check_comment_sa,
    )

    responses.add_callback(
        responses.POST,
        'http://phabricator.test/api/differential.createcomment',
        callback=_check_comment_ccov,
    )

    with mock_phabricator as api:
        revision = Revision(api, mock_try_task)
        revision.lines = {
            # Add dummy lines diff
            'test.txt': [0],
            'test.cpp': [0],
            'another_test.cpp': [41, 42, 43],
        }
        revision.files = ['test.txt', 'test.cpp', 'another_test.cpp']
        reporter = PhabricatorReporter({'analyzers': ['coverage', 'clang-tidy']}, api=api)

    issue_clang_tidy = ClangTidyIssue(revision, 'another_test.cpp', '42', '51', 'modernize-use-nullptr', 'dummy message', 'error')
    assert issue_clang_tidy.is_publishable()

    issue_coverage = CoverageIssue('test.cpp', 0, 'This file is uncovered', revision)
    assert issue_coverage.is_publishable()

    issues, patches = reporter.publish([issue_clang_tidy, issue_coverage, ], revision)
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-2]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'clang-tidy'

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/differential.createcomment'
    assert call.response.headers.get('unittest') == 'coverage'


@responses.activate
def test_phabricator_analyzers(mock_config, mock_phabricator, mock_try_task):
    '''
    Test analyzers filtering on phabricator reporter
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision, ImprovementPatch
    from static_analysis_bot.tasks.clang_format import ClangFormatIssue
    from static_analysis_bot.tasks.infer import InferIssue
    from static_analysis_bot.tasks.clang_tidy import ClangTidyIssue
    from static_analysis_bot.tasks.lint import MozLintIssue
    from static_analysis_bot.tasks.coverage import CoverageIssue

    def _test_reporter(api, analyzers):
        # Always use the same setup, only varies the analyzers
        revision = Revision(api, mock_try_task)
        revision.lines = {
            'test.cpp': [0, 41, 42, 43],
            'dom/test.cpp': [42, ],
        }
        reporter = PhabricatorReporter({'analyzers': analyzers}, api=api)

        issues = [
            ClangFormatIssue('dom/test.cpp', 42, 1, revision),
            ClangTidyIssue(revision, 'test.cpp', '42', '51', 'modernize-use-nullptr', 'dummy message', 'error'),
            InferIssue({
                'file': 'test.cpp',
                'line': 42,
                'column': 1,
                'bug_type': 'dummy',
                'kind': 'whatever',
                'qualifier': 'dummy message.',
            }, revision),
            MozLintIssue('test.cpp', 1, 'danger', 42, 'flake8', 'Python error', 'EXXX', revision),
            CoverageIssue('test.cpp', 0, 'This file is uncovered', revision),
        ]

        assert all(i.is_publishable() for i in issues)

        revision.improvement_patches = [
            ImprovementPatch('dummy', repr(revision), 'Whatever'),
            ImprovementPatch('clang-tidy', repr(revision), 'Some C fixes'),
            ImprovementPatch('clang-format', repr(revision), 'Some lint fixes'),
            ImprovementPatch('infer', repr(revision), 'Some java fixes'),
            ImprovementPatch('mozlint', repr(revision), 'Some js fixes'),
        ]
        list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

        return reporter.publish(issues, revision)

    # Use same instance of api
    with mock_phabricator as api:

        # Skip commenting on phabricator
        # we only care about filtering issues
        api.comment = unittest.mock.Mock(return_value=True)

        # No analyzers at all
        with pytest.raises(AssertionError):
            _test_reporter(api, None)

        # Only clang-tidy
        issues, patches = _test_reporter(api, ['clang-tidy'])
        assert len(issues) == 1
        assert len(patches) == 1
        assert [p.analyzer for p in patches] == ['clang-tidy']

        # Only clang-format
        issues, patches = _test_reporter(api, ['clang-format'])
        assert len(issues) == 1
        assert len(patches) == 1
        assert [p.analyzer for p in patches] == ['clang-format']

        # Only infer
        issues, patches = _test_reporter(api, ['infer'])
        assert len(issues) == 1
        assert len(patches) == 1
        assert [p.analyzer for p in patches] == ['infer']

        # Only mozlint
        issues, patches = _test_reporter(api, ['mozlint'])
        assert len(issues) == 1
        assert len(patches) == 1
        assert [p.analyzer for p in patches] == ['mozlint']

        # Only coverage
        issues, patches = _test_reporter(api, ['coverage'])
        assert len(issues) == 1
        assert len(patches) == 0

        # clang-format + clang-tidy
        issues, patches = _test_reporter(api, ['clang-tidy', 'clang-format'])
        assert len(issues) == 2
        assert len(patches) == 2
        assert [p.analyzer for p in patches] == ['clang-tidy', 'clang-format']

        # All of them
        issues, patches = _test_reporter(api, ['clang-tidy', 'clang-format', 'infer', 'mozlint', 'coverage'])
        assert len(issues) == 5
        assert len(patches) == 4
        assert [p.analyzer for p in patches] == ['clang-tidy', 'clang-format', 'infer', 'mozlint']


@responses.activate
def test_phabricator_harbormaster(mock_phabricator, mock_try_task):
    '''
    Test Phabricator reporter publication on a mock clang-tidy issue
    using harbormaster
    '''
    from static_analysis_bot.report.phabricator import PhabricatorReporter
    from static_analysis_bot.revisions import Revision
    from static_analysis_bot.tasks.clang_tidy import ClangTidyIssue

    def _check_message(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload['output'] == ['json']
        assert len(payload['params']) == 1
        details = json.loads(payload['params'][0])
        assert details == {
            'buildTargetPHID': 'PHID-HMBD-deadbeef12456',
            'lint': [
                {
                    'char': 51,
                    'code': 'clang-tidy.modernize-use-nullptr',
                    'name': 'Clang-Tidy - modernize-use-nullptr',
                    'line': 42,
                    'path': 'test.cpp',
                    'severity': 'warning',
                    'description': 'dummy message'
                }
            ],
            'unit': [],
            'type': 'work',
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
        'http://phabricator.test/api/harbormaster.sendmessage',
        callback=_check_message,
    )

    with mock_phabricator as api:
        revision = Revision(api, mock_try_task)
        revision.lines = {
            # Add dummy lines diff
            'test.cpp': [41, 42, 43],
        }
        revision.build_target_phid = 'PHID-HMBD-deadbeef12456'
        reporter = PhabricatorReporter({'analyzers': ['clang-tidy'], 'mode': 'harbormaster'}, api=api)

    issue = ClangTidyIssue(revision, 'test.cpp', '42', '51', 'modernize-use-nullptr', 'dummy message', 'error')
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue, ], revision)
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == 'http://phabricator.test/api/harbormaster.sendmessage'
    assert call.response.headers.get('unittest') == 'clang-tidy'
