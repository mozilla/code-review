# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import io
import os
import re

import hglib
from parsepatch.patch import Patch

from cli_common import log
from cli_common.phabricator import PhabricatorAPI
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import REPO_REVIEW
from static_analysis_bot.config import settings

logger = log.get_logger(__name__)


class Revision(object):
    '''
    A common DCM revision
    '''
    files = []
    lines = {}
    patch = None
    diff_url = None

    def analyze_patch(self):
        '''
        Analyze loaded patch to extract modified lines
        and statistics
        '''
        assert self.patch is not None, \
            'Missing patch'
        assert isinstance(self.patch, str), \
            'Invalid patch type'

        # List all modified lines from current revision changes
        patch = Patch.parse_patch(self.patch, skip_comments=False)
        assert patch != {}, \
            'Empty patch'
        self.lines = {
            # Use all changes in new files
            filename: diff.get('touched', []) + diff.get('added', [])
            for filename, diff in patch.items()
        }

        # Shortcut to files modified
        self.files = self.lines.keys()

        # Report nb of files and lines analyzed
        stats.api.increment('analysis.files', len(self.files))
        stats.api.increment('analysis.lines', sum(len(line) for line in self.lines.values()))

    def contains(self, issue):
        '''
        Check if the issue is this patch
        '''
        assert isinstance(issue, Issue)

        # Get modified lines for this issue
        modified_lines = self.lines.get(issue.path)
        if modified_lines is None:
            logger.warn('Issue path in not in revision', path=issue.path, revision=self)
            return False

        # Detect if this issue is in the patch
        lines = set(range(issue.line, issue.line + issue.nb_lines))
        return not lines.isdisjoint(modified_lines)

    @property
    def has_clang_files(self):
        '''
        Check if this revision has any file that might
        be a C/C++ file
        '''
        def _is_clang(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.cpp_extensions

        return any(_is_clang(f) for f in self.files)


class PhabricatorRevision(Revision):
    '''
    A phabricator revision to process
    '''
    regex = re.compile(r'^(PHID-DIFF-(?:\w+))$')

    def __init__(self, description, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api

        # Parse Diff description
        match = self.regex.match(description)
        if match is None:
            raise Exception('Invalid Phabricator description')
        groups = match.groups()
        self.diff_phid = groups[0]

        # Load diff details to get the diff revision
        diffs = self.api.search_diffs(diff_phid=self.diff_phid)
        assert len(diffs) == 1, 'No diff available for {}'.format(self.diff_phid)
        diff = diffs[0]

        self.diff_id = diff['id']
        self.phid = diff['revisionPHID']
        self.hg_base = diff['baseRevision']
        revision = self.api.load_revision(self.phid)
        self.id = revision['id']

    @property
    def namespaces(self):
        return [
            'phabricator.{}'.format(self.id),
            'phabricator.diff.{}'.format(self.diff_id),
            'phabricator.phid.{}'.format(self.phid),
            'phabricator.diffphid.{}'.format(self.diff_phid),
        ]

    def __repr__(self):
        return self.diff_phid

    def __str__(self):
        return 'Phabricator #{} - {}'.format(self.diff_id, self.diff_phid)

    @property
    def url(self):
        return 'https://{}/D{}'.format(self.api.hostname, self.id)

    def load(self, repo):
        '''
        Load patch from Phabricator
        '''
        assert isinstance(repo, hglib.client.hgclient)

        # Load raw patch
        self.patch = self.api.load_raw_diff(self.diff_id)

    def apply(self, repo):
        '''
        Apply patch from Phabricator to Mercurial local repository
        '''
        assert isinstance(repo, hglib.client.hgclient)

        # Update the repo to base revision
        try:
            repo.update(
                rev=self.hg_base,
                clean=True,
            )
        except hglib.error.CommandError as e:
            logger.warning('Failed to update to base revision', revision=self.hg_base, error=e)

        # Apply the patch on top of repository
        repo.import_(
            patches=io.BytesIO(self.patch.encode('utf-8')),
            nocommit=True,
        )

    def as_dict(self):
        '''
        Outputs a serializable representation of this revision
        '''
        return {
            'source': 'phabricator',
            'diff_phid': self.diff_phid,
            'phid': self.phid,
            'id': self.id,
            'url': self.url,
            'has_clang_files': self.has_clang_files,
        }


class MozReviewRevision(Revision):
    '''
    A mozreview revision to process
    '''
    def __init__(self, review_request_id, mercurial, diffset_revision):
        self.mercurial = mercurial
        self.review_request_id = int(review_request_id)
        self.diffset_revision = int(diffset_revision)

    def __repr__(self):
        return '{}-{}-{}'.format(
            self.mercurial[:8],
            self.review_request_id,
            self.diffset_revision,
        )

    def __str__(self):
        return 'MozReview #{} - {}'.format(self.review_request_id, self.diffset_revision)

    @property
    def url(self):
        return 'https://reviewboard.mozilla.org/r/{}/'.format(self.review_request_id) # noqa

    @property
    def namespaces(self):
        return [
            'mozreview.{}'.format(self.review_request_id),
            'mozreview.{}.{}'.format(self.review_request_id, self.diffset_revision),
            'mozreview.rev.{}'.format(self.mercurial),
        ]

    def load(self, repo):
        '''
        Load required revision from mercurial remote repo
        The repository will then be set to the ancestor of analysed revision
        '''
        assert isinstance(repo, hglib.client.hgclient)

        # Get top revision
        top = repo.log('reverse(public())', limit=1)[0].node.decode('utf-8')

        # Pull revision from review
        repo.pull(
            source=REPO_REVIEW,
            rev=self.mercurial,
            update=True,
            force=True,
        )

        # Find common ancestor revision
        out = repo.log('ancestor({}, {})'.format(top, self.mercurial))
        assert out is not None and len(out) > 0, \
            'Failed to find ancestor for {}'.format(self.mercurial)
        ancestor = out[0].node.decode('utf-8')
        logger.info('Found HG ancestor', current=self.mercurial, ancestor=ancestor)

        # Load full diff from revision up to ancestor
        # using Git format for compatibility with improvement patch builder
        self.patch = repo.diff(revs=[ancestor, self.mercurial], git=True).decode('utf-8')

        # Move repo to ancestor so we don't trigger an unecessary clobber
        repo.update(rev=ancestor, clean=True)

    def apply(self, repo):
        '''
        Load required revision from mercurial remote repo
        '''
        assert isinstance(repo, hglib.client.hgclient)

        # Update to the target revision
        repo.update(
            rev=self.mercurial,
            clean=True,
        )

    def as_dict(self):
        '''
        Outputs a serializable representation of this revision
        '''
        return {
            'source': 'mozreview',
            'rev': self.mercurial,
            'review_request': self.review_request_id,
            'diffset': self.diffset_revision,
            'url': self.url,
            'has_clang_files': self.has_clang_files,
        }
