# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import hashlib
import os

from static_analysis_bot import Issue


class DummyIssue(Issue):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def as_markdown(self):
        return 'empty'

    def as_text(self):
        return 'empty'

    def as_dict(self):
        return {}

    def as_phabricator_lint(self):
        return {}

    def validates(self):
        return False


def test_cmp():
    '''
    Test issues comparisons (__eq__)
    '''

    # Base args
    a = DummyIssue(path='test.cpp', lines_hash='xxx')
    b = DummyIssue(path='test.cpp', lines_hash='xxx')
    assert a == b
    a = DummyIssue(path='test.cpp', lines_hash='123')
    b = DummyIssue(path='test.cpp', lines_hash='345')
    assert a != b

    # Different classes
    class AnotherIssue(DummyIssue):
        pass

    a = AnotherIssue(path='test.cpp', lines_hash='deadbeef')
    b = DummyIssue(path='test.cpp', lines_hash='deadbeef')
    assert a != b

    # Extra identifiers
    class ExtraIssue(DummyIssue):
        def build_extra_identifiers(self):
            return {
                'somekey': self.extra,
            }

    a = ExtraIssue(path='test.cpp', lines_hash='xxx', extra='a')
    b = ExtraIssue(path='test.cpp', lines_hash='xxx', extra='a')
    assert a == b
    a = ExtraIssue(path='test.cpp', lines_hash='xxx', extra='a')
    b = ExtraIssue(path='test.cpp', lines_hash='xxx', extra='XXX')
    assert a != b
    b = ExtraIssue(path='test.cpp', lines_hash='xxx', extra=1)
    a = ExtraIssue(path='test.cpp', lines_hash='xxx', extra=None)
    assert a != b


def test_set():
    '''
    Test issues sets (__hash__)
    '''

    # Build a first set
    X = set()
    a = DummyIssue(path='test.cpp', lines_hash='ABC')
    X.add(a)
    assert len(X) == 1
    X.add(a)
    assert len(X) == 1
    b = DummyIssue(path='another.cpp', lines_hash='XYZ')
    X.add(b)
    assert len(X) == 2

    # Build another set
    Y = {
        DummyIssue(path='test.cpp', lines_hash='ABC'),
        DummyIssue(path='lib.h', lines_hash='ABCD'),
    }
    assert len(Y) == 2

    # Calc difference
    diff = Y.difference(X)
    assert len(diff) == 1
    paths = [i.path for i in diff]
    assert paths == ['lib.h', ]

    # Calc symmetric difference
    diff = Y.symmetric_difference(X)
    assert len(diff) == 2
    paths = [i.path for i in diff]
    assert 'lib.h' in paths
    assert 'another.cpp' in paths


def test_lines_hash(mock_config, test_cpp):
    '''
    Test issues line hashing
    '''
    from static_analysis_bot import Issue

    class TestIssue(DummyIssue):
        def __init__(self, **kwargs):
            kwargs.setdefault('nb_lines', 1)
            kwargs.setdefault('path', 'test.cpp')
            super().__init__(**kwargs)

    def assert_hash(issue, content, hash_start):
        assert isinstance(issue, Issue)
        assert isinstance(content, str)
        assert isinstance(hash_start, str)

        # Build hash for content
        valid_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        # Check hash itself
        assert valid_hash.startswith(hash_start)

        # Compare hash
        assert issue.build_lines_hash() == valid_hash

    # Simple tests
    a = TestIssue(line=1)
    assert_hash(a, 'include <cstdio>\n', '2687b6e5')
    b = TestIssue(line=2)
    assert_hash(b, '', 'e3b0c442')
    c = TestIssue(line=1, nb_lines=3)
    assert_hash(c, 'include <cstdio>\nint main(void){\n', '108c43f3')

    assert len({a, b, c}) == 3

    # Test indentation changes
    indent = TestIssue(line=1, path='indent.c')
    path = os.path.join(mock_config.repo_dir, indent.path)
    with open(path, 'w') as f:
        f.write('A nicely indented code.')
    assert_hash(indent, 'A nicely indented code.', 'bc99170a')

    # Update indentation, should not change
    with open(path, 'w') as f:
        f.write('          A nicely indented code.')
    assert_hash(indent, 'A nicely indented code.', 'bc99170a')

    # Even with tabs
    with open(path, 'w') as f:
        f.write('\t  \t A nicely indented code.')
    assert_hash(indent, 'A nicely indented code.', 'bc99170a')

    # Same hash with same line at different places
    path = os.path.join(mock_config.repo_dir, 'another.h')
    with open(path, 'w') as f:
        f.write('another line\n')
        f.write('      another line\n')
        f.write(' \t another line\n')
        f.write('\t  \t another line\n')

    for line in range(1, 5):
        assert_hash(TestIssue(line=line, path='another.h'), 'another line\n', 'b1401bec')


def test_allowed_paths(mock_config, mock_repository):
    '''
    Test allowed paths for ClangFormatIssue
    The test config has these 2 rules: dom/* and tests/*.py
    '''
    from static_analysis_bot.clang.format import ClangFormatIssue

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
