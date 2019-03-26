# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os.path
from unittest.mock import MagicMock

import responses
from parsepatch.patch import Patch


@responses.activate
def test_phabricator(mock_phabricator, mock_repository, mock_config):
    '''
    Test a phabricator revision
    '''
    from static_analysis_bot.revisions import PhabricatorRevision

    with mock_phabricator as api:
        r = PhabricatorRevision(api, 'PHID-DIFF-testABcd12')
    assert not hasattr(r, 'mercurial')
    assert r.diff_id == 42
    assert r.diff_phid == 'PHID-DIFF-testABcd12'
    assert r.url == 'https://phabricator.test/D51'
    assert repr(r) == 'PHID-DIFF-testABcd12'
    assert r.id == 51  # revision

    # Check test.txt content
    test_txt = os.path.join(mock_config.repo_dir, 'test.txt')
    assert open(test_txt).read() == 'Hello World\n'

    # Cleanup the repo
    mock_repository.update(clean=True)

    # Load full patch
    # Mock the mercurial repo update as we use a dummy revision
    assert r.patch is None
    __update = mock_repository.update
    mock_repository.update = MagicMock(return_value=True)
    r.load(mock_repository)
    mock_repository.update = __update
    assert r.patch is not None
    assert isinstance(r.patch, str)
    assert len(r.patch.split('\n')) == 14
    patch = Patch.parse_patch(r.patch)
    assert patch == {
        'test.txt': {
            'touched': [],
            'deleted': [],
            'added': [2],
            'new': False
        },
        'test.cpp': {
            'touched': [],
            'deleted': [],
            'added': [2],
            'new': False
        }
    }

    # Check file is untouched after load
    assert open(test_txt).read() == 'Hello World\n'

    # Check file is updated after apply
    r.apply(mock_repository)
    assert open(test_txt).read() == 'Hello World\nSecond line\n'


def test_clang_files(mock_revision):
    '''
    Test clang files detection
    '''
    assert mock_revision.files == []
    assert not mock_revision.has_clang_files

    mock_revision.files = ['test.cpp', 'test.h']
    assert mock_revision.has_clang_files

    mock_revision.files = ['test.py', 'test.js']
    assert not mock_revision.has_clang_files

    mock_revision.files = ['test.cpp', 'test.js', 'xxx.txt']
    assert mock_revision.has_clang_files

    mock_revision.files = ['test.h', 'test.js', 'xxx.txt']
    assert not mock_revision.has_clang_files

    assert mock_revision.has_clang_header_files


def test_analyze_patch():
    from static_analysis_bot.revisions import Revision
    from static_analysis_bot import Issue

    class MyIssue(Issue):
        def __init__(self, path, line):
            self.path = path
            self.line = line
            self.nb_lines = 1

        def as_dict():
            return {}

        def as_markdown():
            return ''

        def as_text():
            return ''

        def validates():
            return True

        def as_phabricator_lint():
            return {}

    issue_in_new_file = MyIssue('new.txt', 1)
    issue_in_existing_file_touched_line = MyIssue('modified.txt', 3)
    issue_in_existing_file_not_changed_line = MyIssue('modified.txt', 1)
    issue_in_existing_file_added_line = MyIssue('added.txt', 4)
    issue_in_not_changed_file = MyIssue('notexisting.txt', 1)

    rev = Revision()
    rev.patch = '''
diff --git a/new.txt b/new.txt
new file mode 100644
index 00000000..83db48f8
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,3 @@
+line1
+line2
+line3
diff --git a/modified.txt b/modified.txt
index 84275f99..cbc9b72a 100644
--- a/modified.txt
+++ b/modified.txt
@@ -1,4 +1,4 @@
 line1
 line2
-line3
+line7
 line4
diff --git a/added.txt b/added.txt
index 83db48f8..84275f99 100644
--- a/added.txt
+++ b/added.txt
@@ -1,3 +1,4 @@
 line1
 line2
 line3
+line4
'''

    rev.analyze_patch()
    assert 'new.txt' in rev.lines
    assert rev.lines['new.txt'] == [1, 2, 3]
    assert 'modified.txt' in rev.lines
    assert rev.lines['modified.txt'] == [3]
    assert 'added.txt' in rev.lines
    assert rev.lines['added.txt'] == [4]
    assert 'new.txt' in rev.files
    assert 'modified.txt' in rev.files
    assert 'added.txt' in rev.files

    assert rev.contains(issue_in_new_file)
    assert rev.contains(issue_in_existing_file_touched_line)
    assert not rev.contains(issue_in_existing_file_not_changed_line)
    assert rev.contains(issue_in_existing_file_added_line)
    assert not rev.contains(issue_in_not_changed_file)
