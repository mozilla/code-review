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
        r = PhabricatorRevision('PHID-DIFF-testABcd12', api)
    assert not hasattr(r, 'mercurial')
    assert r.diff_id == 42
    assert r.diff_phid == 'PHID-DIFF-testABcd12'
    assert r.url == 'https://phabricator.test/D51'
    assert repr(r) == 'PHID-DIFF-testABcd12'
    assert r.id == 51  # revision

    # Check test.txt content
    test_txt = os.path.join(mock_config.repo_dir, 'test.txt')
    assert open(test_txt).read() == 'Hello World\n'

    # Load full patch
    # Mock the mercurial repo update as we use a dummy revision
    assert r.patch is None
    __update = mock_repository.update
    mock_repository.update = MagicMock(return_value=True)
    r.load(mock_repository)
    mock_repository.update = __update
    assert r.patch is not None
    assert isinstance(r.patch, str)
    assert len(r.patch.split('\n')) == 7
    patch = Patch.parse_patch(r.patch)
    assert patch == {
        'test.txt': {
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
    assert mock_revision.has_clang_files
