# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os


def test_flake8_rules(tmpdir, mock_config, mock_revision):
    '''
    Check flake8 rule detection
    '''
    from static_analysis_bot.lint import MozLintIssue

    # Build fake python files
    path = os.path.join(mock_config.repo_dir, 'test.py')
    with open(path, 'w') as f:
        f.write('print("TEST")')

    path = os.path.join(mock_config.repo_dir, 'test/dummy/XXX.py')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('print("TEST 2")')

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


def test_issue_path(mock_repository, mock_config, mock_revision):
    '''
    A mozlint issue can be absolute or relative
    But the path sent to reporters must always be relative
    '''
    from static_analysis_bot.lint import MozLintIssue

    relative_path = 'test.txt'
    issue = MozLintIssue(relative_path, 1, 'error', 1, 'dummy', 'Any error', 'XXX', mock_revision)
    assert issue.path == 'test.txt'

    absolute_path = os.path.join(mock_config.repo_dir, relative_path)
    issue = MozLintIssue(absolute_path, 1, 'error', 1, 'dummy', 'Any error', 'XXX', mock_revision)
    assert issue.path == 'test.txt'


def test_as_text(mock_revision):
    '''
    Test text export for ClangTidyIssue
    '''
    from static_analysis_bot.lint import MozLintIssue
    issue = MozLintIssue('test.py', 1, 'error', 1, 'flake8', 'dummy test withUppercaseChars', 'dummy rule', mock_revision)

    assert issue.as_text() == 'Error: Dummy test withUppercaseChars [flake8: dummy rule]'
