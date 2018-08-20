# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os.path

import responses
from parsepatch.patch import Patch


def test_mozreview():
    '''
    Test a mozreview revision
    '''
    from static_analysis_bot.revisions import MozReviewRevision

    r = MozReviewRevision('164530', '308c22e7899048467002de4ffb126cac0875c994', '7')
    assert r.mercurial == '308c22e7899048467002de4ffb126cac0875c994'
    assert r.review_request_id == 164530
    assert r.diffset_revision == 7
    assert r.url == 'https://reviewboard.mozilla.org/r/164530/'
    assert repr(r) == '308c22e7-164530-7'


@responses.activate
def test_phabricator(mock_phabricator, mock_repository, mock_config):
    '''
    Test a phabricator revision
    '''
    from static_analysis_bot.revisions import PhabricatorRevision
    from static_analysis_bot.report.phabricator import PhabricatorReporter

    api = PhabricatorReporter({
        'url': 'http://phabricator.test/api/',
        'api_key': 'deadbeef',
    })

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
    assert r.patch is None
    r.load(mock_repository)
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


def test_mercurial_patch(mock_config, mock_repository):
    '''
    Test mercurial patch creation
    '''
    from static_analysis_bot.revisions import MozReviewRevision

    def _commit(name, public=True):
        path = os.path.join(mock_config.repo_dir, 'review_{}.txt'.format(name))
        with open(path, 'w') as f:
            f.write('Review commit {}'.format(name))
        mock_repository.add(path.encode('utf-8'))
        msg = 'Content commit {}'.format(name).encode('utf-8')
        _, node = mock_repository.commit(msg, user=b'Tester')
        mock_repository.phase(node, public=public)
        return node

    # Add an initial commit to exclude
    assert mock_repository.branch() == b'default'
    _commit('base')

    # Create a branch
    mock_repository.branch(b'test-review')

    # Add some commits on test-review
    commits = [_commit(i, public=False) for i in range(5)]
    revision = commits[-1]

    # Revert to default
    mock_repository.update(b'default', clean=True)

    # Add a new tip
    tip = _commit('exclude')
    assert mock_repository.tip().node == tip

    # Load the revision
    mozrev = MozReviewRevision('12345', revision.decode('utf-8'), '1')
    mozrev.load(mock_repository)
    mozrev.analyze_patch()

    # Check the review has all 5 files impacted by branch
    # but does not have the exclude or base, or anything previous
    assert mozrev.files == {'review_0.txt', 'review_1.txt', 'review_2.txt', 'review_3.txt', 'review_4.txt'}
