# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


def test_allowed_paths(mock_config):
    '''
    Test allowed paths for ClangFormatIssue
    The test config has these 2 rules: dom/* and tests/*.py
    '''
    from static_analysis_bot.tasks.clang_format import ClangFormatIssue

    def _allowed(path):
        # Build an issue and check its validation
        # that will trigger the path validation
        issue = ClangFormatIssue(path, 1, 1, None)
        return issue.validates()

    checks = {
        'nope.cpp': False,
        'dom/whatever.cpp': True,
        'dom/sub/folders/whatever.cpp': True,
        'dom/noext': True,
        'dom_fail.h': False,
        'tests/xxx.pyc': False,
        'tests/folder/part/1.py': True,
    }
    for path, result in checks.items():
        assert _allowed(path) is result
