# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import io
import os
from datetime import timedelta

import hglib
from parsepatch.patch import Patch

from cli_common import log
from cli_common.phabricator import BuildState
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import create_blob_artifact
from static_analysis_bot import AnalysisException
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import REPO_TRY
from static_analysis_bot.config import SOURCE_TRY
from static_analysis_bot.config import settings

logger = log.get_logger(__name__)


class ImprovementPatch(object):
    '''
    An improvement patch built by the bot
    '''
    def __init__(self, analyzer_name, patch_name, content):
        # Build name from analyzer and revision
        self.analyzer = analyzer_name
        self.name = '{}-{}.diff'.format(analyzer_name, patch_name)
        self.content = content
        self.url = None
        self.path = None

    def __str__(self):
        return '{}: {}'.format(self.analyzer, self.url or self.path or self.name)

    def write(self):
        '''
        Write patch on local FS, for dev & tests only
        '''
        self.path = os.path.join(settings.taskcluster.results_dir, self.name)
        with open(self.path, 'w') as f:
            length = f.write(self.content)
            logger.info('Improvement patch saved', path=self.path, length=length)

    def publish(self, queue_service, days_ttl=30):
        '''
        Push through Taskcluster API to setup the content-type header
        so it displays nicely in browsers
        '''
        assert not settings.taskcluster.local, 'Only publish on online Taskcluster tasks'
        self.url = create_blob_artifact(
            queue_service,
            task_id=settings.taskcluster.task_id,
            run_id=settings.taskcluster.run_id,
            path='public/patch/{}'.format(self.name),
            content=self.content,
            content_type='text/plain; charset=utf-8',  # Displays instead of download):
            ttl=timedelta(days=days_ttl - 1),
        )
        logger.info('Improvement patch published', url=self.url)


class Revision(object):
    '''
    A common DCM revision
    '''
    def __init__(self):
        self.files = []
        self.lines = {}
        self.patch = None
        self.improvement_patches = []

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

    def has_file(self, path):
        '''
        Check if the path is in this patch
        '''
        assert isinstance(path, str)
        return path in self.files

    def contains(self, issue):
        '''
        Check if the issue (path+lines) is in this patch
        '''
        assert isinstance(issue, Issue)

        # Get modified lines for this issue
        modified_lines = self.lines.get(issue.path)
        if modified_lines is None:
            logger.warn('Issue path is not in revision', path=issue.path, revision=self)
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

    @property
    def has_clang_header_files(self):
        '''
        Check if this revision has any file that might
        be a C/C++ header file
        '''
        def _is_clang_header(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.cpp_header_extensions

        return any(_is_clang_header(f) for f in self.files)

    @property
    def has_idl_files(self):
        '''
        Check if this revision has any idl files
        '''
        def _is_idl(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.idl_extenssions

        return any(_is_idl(f) for f in self.files)

    @property
    def has_infer_files(self):
        '''
        Check if this revision has any file that might
        be a Java file
        '''
        def _is_infer(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.java_extensions

        return any(_is_infer(f) for f in self.files)

    def add_improvement_patch(self, analyzer_name, content):
        '''
        Save an improvement patch, and make it available
        as a Taskcluster artifact
        '''
        assert isinstance(content, str)
        assert len(content) > 0
        self.improvement_patches.append(
            ImprovementPatch(analyzer_name, repr(self), content)
        )

    def reset(self):
        '''
        Reset temporary data in BEFORE mode
        * improvement patches
        '''
        self.improvement_patches = []


class PhabricatorRevision(Revision):
    '''
    A phabricator revision to process
    '''
    diff_phid = None
    build_target_phid = None

    def __init__(self, api, diff_phid=None, try_task=None):
        super().__init__()
        assert isinstance(api, PhabricatorAPI)
        assert (diff_phid is not None) ^ (try_task is not None)
        self.api = api
        self.mercurial_revision = None

        if diff_phid is not None:
            # Load directly from the diff phid
            self.load_phabricator(diff_phid)
        elif try_task is not None:
            # Load build target phid from the task env
            # And get the diff from the phabricator api
            build_target = try_task['extra']['code-review']['phabricator-diff']
            buildable = self.api.find_target_buildable(build_target)
            self.load_phabricator(buildable['fields']['objectPHID'], build_target)
        else:
            raise Exception('Invalid revision configuration')

    def load_phabricator(self, diff_phid, build_target=None):
        '''
        Load identifiers from Phabricator
        '''
        assert diff_phid.startswith('PHID-DIFF-')
        self.diff_phid = diff_phid

        # Load diff details to get the diff revision
        diffs = self.api.search_diffs(diff_phid=self.diff_phid)
        assert len(diffs) == 1, 'No diff available for {}'.format(self.diff_phid)
        self.diff = diffs[0]
        self.diff_id = self.diff['id']
        self.phid = self.diff['revisionPHID']

        self.revision = self.api.load_revision(self.phid)
        self.id = self.revision['id']

        # Load build for status updates
        hm_target = os.environ.get('HARBORMASTER_TARGET')
        if build_target is not None:
            self.build_target_phid = build_target
        elif hm_target and isinstance(hm_target, str) and hm_target.startswith('PHID-'):
            self.build_target_phid = hm_target
        elif settings.build_plan:
            build, targets = self.api.find_diff_build(self.diff_phid, settings.build_plan)
            build_phid = build['phid']
            nb = len(targets)
            assert nb > 0, 'No build target found'
            if nb > 1:
                logger.warn('More than 1 build target found !', nb=nb, build_phid=build_phid)
            target = targets[0]
            self.build_target_phid = target['phid']
        else:
            logger.info('No build plan specified, no HarborMaster update')

        # Load target patch from Phabricator for Try mode
        if settings.source == SOURCE_TRY:
            self.patch = self.api.load_raw_diff(self.diff_id)

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

    def update_status(self, state, lint_issues=[]):
        '''
        Update build status on HarborMaster
        '''
        assert isinstance(state, BuildState)
        assert isinstance(lint_issues, list)
        if not self.build_target_phid:
            logger.info('No build target found, skipping HarborMaster update', state=state.value)
            return

        self.api.update_build_target(
            self.build_target_phid,
            state,
            lint=lint_issues,
        )
        logger.info('Updated HarborMaster status', state=state)

    def setup_try(self, tasks):
        '''
        Find the mercurial revision from the Try decision task env
        '''
        # Find the decision task
        def is_decision_task(task):
            image = task['task']['payload'].get('image')
            if image is not None and isinstance(image, str):
                return image.startswith('taskcluster/decision')
        decision_task = next(filter(is_decision_task, tasks.values()), None)
        assert decision_task is not None, 'Missing decision task'

        # Use mercurial infos for local revision
        decision_env = decision_task['task']['payload']['env']
        assert decision_env.get('GECKO_HEAD_REPOSITORY') == REPO_TRY.decode('utf-8'), \
            'Not the try repo in GECKO_HEAD_REPOSITORY'

        # Save mercurial revision
        self.mercurial_revision = decision_env.get('GECKO_HEAD_REV')
        assert self.mercurial_revision is not None, 'Missing try revision'
        logger.info('Using Try mercurial revision', rev=self.mercurial_revision)

    def load(self, repo):
        '''
        Load full raw patch from Phabricator API then load and apply
        the dependant stack of patches from Phabricator
        when the patch is not already in the repository
        '''
        try:
            _, patches = self.api.load_patches_stack(repo, self.diff)
        except Exception as e:
            raise AnalysisException('mercurial', str(e))

        # Expose current patch to workflow
        self.patch = dict(patches)[self.diff_phid]

        # Skip patch application when repo already has the patch
        if self.mercurial_revision is not None:
            return

        # Apply all patches from base to top
        # except our current (top) patch
        for diff_phid, patch in patches[:-1]:
            logger.info('Applying parent diff', phid=diff_phid)
            try:
                repo.import_(
                    patches=io.BytesIO(patch.encode('utf-8')),
                    message='SA Imported patch {}'.format(diff_phid),
                    user='reviewbot',
                )
            except hglib.error.CommandError:
                raise AnalysisException('mercurial', 'Failed to import parent patch {}'.format(diff_phid))

    def apply(self, repo):
        '''
        Apply patch from Phabricator to Mercurial local repository
        '''
        assert isinstance(repo, hglib.client.hgclient)

        if self.mercurial_revision:
            # Apply the existing commit when available
            repo.update(
                rev=self.mercurial_revision,
                clean=True,
            )
        else:
            # Apply the patch on top of repository
            try:
                repo.import_(
                    patches=io.BytesIO(self.patch.encode('utf-8')),
                    message='SA Analyzed patch',
                    user='reviewbot',
                )
                logger.info('Applied target patch', phid=self.diff_phid)
            except hglib.error.CommandError:
                raise AnalysisException('mercurial', 'Failed to import target patch')

    def as_dict(self):
        '''
        Outputs a serializable representation of this revision
        '''
        return {
            'diff_phid': self.diff_phid,
            'phid': self.phid,
            'diff_id': self.diff_id,
            'id': self.id,
            'url': self.url,
            'has_clang_files': self.has_clang_files,

            # Extra infos for frontend
            'title': self.revision['fields'].get('title'),
            'bugzilla_id': self.revision['fields'].get('bugzilla.bug-id'),
        }
