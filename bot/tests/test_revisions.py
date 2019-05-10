# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import responses
from parsepatch.patch import Patch


@responses.activate
def test_phabricator(mock_config, mock_revision):
    '''
    Test a phabricator revision
    '''
    assert not hasattr(mock_revision, 'mercurial')
    assert mock_revision.diff_id == 42
    assert mock_revision.diff_phid == 'PHID-DIFF-test'
    assert mock_revision.url == 'https://phabricator.test/D51'
    assert repr(mock_revision) == 'PHID-DIFF-test'
    assert mock_revision.id == 51  # revision

    # Patch is automatically loaded from Phabricator
    assert mock_revision.patch is not None
    assert isinstance(mock_revision.patch, str)
    assert len(mock_revision.patch.split('\n')) == 14
    patch = Patch.parse_patch(mock_revision.patch)
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


def test_analyze_patch(mock_revision):
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

    mock_revision.patch = '''
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

    mock_revision.analyze_patch()
    assert 'new.txt' in mock_revision.lines
    assert mock_revision.lines['new.txt'] == [1, 2, 3]
    assert 'modified.txt' in mock_revision.lines
    assert mock_revision.lines['modified.txt'] == [3]
    assert 'added.txt' in mock_revision.lines
    assert mock_revision.lines['added.txt'] == [4]
    assert 'new.txt' in mock_revision.files
    assert 'modified.txt' in mock_revision.files
    assert 'added.txt' in mock_revision.files

    assert mock_revision.has_file('new.txt')
    assert mock_revision.has_file('modified.txt')
    assert mock_revision.has_file('added.txt')
    assert not mock_revision.has_file('notexisting.txt')

    assert mock_revision.contains(issue_in_new_file)
    assert mock_revision.contains(issue_in_existing_file_touched_line)
    assert not mock_revision.contains(issue_in_existing_file_not_changed_line)
    assert mock_revision.contains(issue_in_existing_file_added_line)
    assert not mock_revision.contains(issue_in_not_changed_file)
