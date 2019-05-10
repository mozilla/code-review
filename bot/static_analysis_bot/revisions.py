# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from datetime import timedelta

from parsepatch.patch import Patch

from cli_common import log
from cli_common.phabricator import BuildState
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import create_blob_artifact
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import REPO_TRY
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
    A Phabricator revision to analyze and report on
    '''
    def __init__(self, api, try_task, update_build=True):
        assert isinstance(api, PhabricatorAPI)
        assert isinstance(try_task, dict)
        self.files = []
        self.lines = {}
        self.patch = None
        self.improvement_patches = []
        self.diff_phid = None
        self.build_target_phid = None
        self.api = api
        self.mercurial_revision = None
        self.update_build = update_build
        self.load_phabricator(try_task)

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

    def load_phabricator(self, try_task):
        '''
        Load identifiers from Phabricator, using the remote task description
        '''
        # Load build target phid from the task env
        self.build_target_phid = try_task['extra']['code-review']['phabricator-diff']
        assert self.build_target_phid.startswith('PHID-HMBT-')

        # And get the diff from the phabricator api
        buildable = self.api.find_target_buildable(self.build_target_phid)
        self.diff_phid = buildable['fields']['objectPHID']
        assert self.diff_phid.startswith('PHID-DIFF-')

        # Load diff details to get the diff revision
        diffs = self.api.search_diffs(diff_phid=self.diff_phid)
        assert len(diffs) == 1, 'No diff available for {}'.format(self.diff_phid)
        self.diff = diffs[0]
        self.diff_id = self.diff['id']
        self.phid = self.diff['revisionPHID']

        self.revision = self.api.load_revision(self.phid)
        self.id = self.revision['id']

        # Load target patch from Phabricator for Try mode
        self.patch = self.api.load_raw_diff(self.diff_id)

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

    def update_status(self, state, lint_issues=[]):
        '''
        Update build status on HarborMaster
        '''
        assert isinstance(state, BuildState)
        assert isinstance(lint_issues, list)
        if not self.build_target_phid:
            logger.info('No build target found, skipping HarborMaster update', state=state.value)
            return

        if not self.update_build:
            logger.info('Update build disabled, skipping HarborMaster update', state=state.value)
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
