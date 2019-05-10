# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


def test_flake8_rules(mock_config, mock_revision):
    '''
    Check flake8 rule detection
    '''
    from static_analysis_bot.tasks.lint import MozLintIssue

    # Valid issue
    issue = MozLintIssue('test.py', 1, 'error', 1, 'flake8', 'Dummy test', 'dummy rule', mock_revision)
    assert not issue.is_disabled_rule()
    assert issue.validates()

    # 3rd party
    issue = MozLintIssue('test/dummy/XXX.py', 1, 'error', 1, 'flake8', 'Dummy test', 'dummy rule', mock_revision)
    assert not issue.is_disabled_rule()
    assert issue.is_third_party()
    assert not issue.validates()

    # Flake8 bad quotes
    issue = MozLintIssue('test.py', 1, 'error', 1, 'flake8', 'Remove bad quotes or whatever.', 'Q000', mock_revision)
    assert issue.is_disabled_rule()
    assert not issue.validates()


def test_as_text(mock_config, mock_revision):
    '''
    Test text export for ClangTidyIssue
    '''
    from static_analysis_bot.tasks.lint import MozLintIssue

    issue = MozLintIssue('test.py', 1, 'error', 1, 'flake8', 'dummy test withUppercaseChars', 'dummy rule', mock_revision)

    assert issue.as_text() == 'Error: Dummy test withUppercaseChars [flake8: dummy rule]'

    assert issue.as_phabricator_lint() == {
        'char': 1,
        'code': 'flake8.dummy rule',
        'line': 1,
        'name': 'MozLint Flake8 - dummy rule',
        'description': 'dummy test withUppercaseChars',
        'path': 'test.py',
        'severity': 'error',
    }
