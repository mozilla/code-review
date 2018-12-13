# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import os
from datetime import datetime
from datetime import timedelta

import hglib

from cli_common.command import run_check
from cli_common.log import get_logger
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import TASKCLUSTER_DATE_FORMAT
from static_analysis_bot import CLANG_FORMAT
from static_analysis_bot import CLANG_TIDY
from static_analysis_bot import INFER
from static_analysis_bot import MOZLINT
from static_analysis_bot import AnalysisException
from static_analysis_bot import stats
from static_analysis_bot.clang import setup as setup_clang
from static_analysis_bot.clang.format import ClangFormat
from static_analysis_bot.clang.tidy import ClangTidy
from static_analysis_bot.config import REPO_UNIFIED
from static_analysis_bot.config import Publication
from static_analysis_bot.config import settings
from static_analysis_bot.infer import setup as setup_infer
from static_analysis_bot.infer.infer import Infer
from static_analysis_bot.lint import MozLint
from static_analysis_bot.report.debug import DebugReporter
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

TASKCLUSTER_NAMESPACE = 'project.releng.services.project.{channel}.static_analysis_bot.{name}'
TASKCLUSTER_INDEX_TTL = 7  # in days


class Workflow(object):
    '''
    Static analysis workflow
    '''
    def __init__(self, reporters, analyzers, index_service, queue_service, phabricator_api):
        assert isinstance(analyzers, list)
        assert len(analyzers) > 0, \
            'No analyzers specified, will not run.'
        self.analyzers = analyzers
        assert 'MOZCONFIG' in os.environ, \
            'Missing MOZCONFIG in environment'

        # Use share phabricator API client
        assert isinstance(phabricator_api, PhabricatorAPI)
        self.phabricator = phabricator_api

        # Load reporters to use
        self.reporters = reporters
        if not self.reporters:
            logger.warn('No reporters configured, this analysis will not be published')

        # Always add debug reporter and Diff reporter
        self.reporters['debug'] = DebugReporter(output_dir=settings.taskcluster.results_dir)

        # Use TC services client
        self.index_service = index_service
        self.queue_service = queue_service

    @stats.api.timed('runtime.clone')
    def clone(self):
        '''
        Clone mozilla-unified
        '''
        logger.info('Clone mozilla unified', dir=settings.repo_dir)
        cmd = hglib.util.cmdbuilder('robustcheckout',
                                    REPO_UNIFIED,
                                    settings.repo_dir,
                                    purge=True,
                                    sharebase=settings.repo_shared_dir,
                                    branch=b'central')

        cmd.insert(0, hglib.HGPATH)
        proc = hglib.util.popen(cmd)
        out, err = proc.communicate()
        if proc.returncode:
            raise hglib.error.CommandError(cmd, proc.returncode, out, err)

        # Open new hg client
        client = hglib.open(settings.repo_dir)

        # Store MC top revision after robustcheckout
        self.top_revision = client.log('reverse(public())', limit=1)[0].node
        logger.info('Mozilla unified top revision', revision=self.top_revision)

        return client

    def run(self, revision):
        '''
        Run the static analysis workflow:
         * Pull revision from review
         * Checkout revision
         * Run static analysis
         * Publish results
        '''
        analyzers = []

        # Index ASAP Taskcluster task for this revision
        self.index(revision, state='started')

        # Add log to find Taskcluster task in papertrail
        logger.info(
            'New static analysis',
            taskcluster_task=settings.taskcluster.task_id,
            taskcluster_run=settings.taskcluster.run_id,
            channel=settings.app_channel,
            publication=settings.publication.name,
            revision=str(revision),
        )
        stats.api.event(
            title='Static analysis on {} for {}'.format(settings.app_channel, revision),
            text='Task {} #{}'.format(settings.taskcluster.task_id, settings.taskcluster.run_id),
        )
        stats.api.increment('analysis')

        with stats.api.timer('runtime.mercurial'):
            try:
                # Start by cloning the mercurial repository
                self.hg = self.clone()
                self.index(revision, state='cloned')

                # Force cleanup to reset top of MU
                # otherwise previous pull are there
                self.hg.update(rev=self.top_revision, clean=True)
                logger.info('Set repo back to Mozilla unified top', rev=self.hg.identify())
            except hglib.error.CommandError as e:
                raise AnalysisException('mercurial', str(e))

            # Load and analyze revision patch
            revision.load(self.hg)
            revision.analyze_patch()

        with stats.api.timer('runtime.mach'):
            # Only run mach if revision has any C/C++ or Java files
            if revision.has_clang_files:

                # Mach pre-setup with mozconfig
                try:
                    logger.info('Mach configure...')
                    with stats.api.timer('runtime.mach.configure'):
                        run_check(['gecko-env', './mach', 'configure'], cwd=settings.repo_dir)

                    logger.info('Mach compile db...')
                    with stats.api.timer('runtime.mach.build-backend'):
                        run_check(['gecko-env', './mach', 'build-backend', '--backend=CompileDB'], cwd=settings.repo_dir)

                    logger.info('Mach pre-export...')
                    with stats.api.timer('runtime.mach.pre-export'):
                        run_check(['gecko-env', './mach', 'build', 'pre-export'], cwd=settings.repo_dir)

                    logger.info('Mach export...')
                    with stats.api.timer('runtime.mach.export'):
                        run_check(['gecko-env', './mach', 'build', 'export'], cwd=settings.repo_dir)
                except Exception as e:
                    raise AnalysisException('mach', str(e))

                # Download clang build from Taskcluster
                # Use new clang-tidy paths, https://bugzilla.mozilla.org/show_bug.cgi?id=1495641
                logger.info('Setup Taskcluster clang build...')
                setup_clang(repository='mozilla-inbound', revision='revision.874a07fdb045b725edc2aaa656a8620ff439ec10')

                # Use clang-tidy & clang-format
                if CLANG_TIDY in self.analyzers:
                    analyzers.append(ClangTidy)
                else:
                    logger.info('Skip clang-tidy')
                if CLANG_FORMAT in self.analyzers:
                    analyzers.append(ClangFormat)
                else:
                    logger.info('Skip clang-format')

            if revision.has_infer_files:
                if INFER in self.analyzers:
                    analyzers.append(Infer)
                    logger.info('Setup Taskcluster infer build...')
                    setup_infer(self.index_service)
                else:
                    logger.info('Skip infer')

            if not (revision.has_clang_files or revision.has_infer_files):
                logger.info('No clang or java files detected, skipping mach, infer and clang-*')

            # Setup python environment
            logger.info('Mach lint setup...')
            cmd = ['gecko-env', './mach', 'lint', '--list']
            with stats.api.timer('runtime.mach.lint'):
                out = run_check(cmd, cwd=settings.repo_dir)
            if 'error: problem with lint setup' in out.decode('utf-8'):
                raise AnalysisException('mach', 'Mach lint setup failed')

            # Always use mozlint
            if MOZLINT in self.analyzers:
                analyzers.append(MozLint)
            else:
                logger.info('Skip mozlint')

        if not analyzers:
            logger.error('No analyzers to use on revision')
            return

        self.index(revision, state='analyzing')
        with stats.api.timer('runtime.issues'):
            # Detect initial issues (and clean up again)
            if settings.publication == Publication.BEFORE_AFTER:
                before_patch = self.detect_issues(analyzers, revision)
                logger.info('Detected {} issue(s) before patch'.format(len(before_patch)))
                stats.api.increment('analysis.issues.before', len(before_patch))
                self.hg.revert(settings.repo_dir.encode('utf-8'), all=True)
                logger.info('Reverted all uncommitted changes in repo', rev=self.hg.identify())

            # Apply patch
            revision.apply(self.hg)

            # Detect new issues
            issues = self.detect_issues(analyzers, revision)
            logger.info('Detected {} issue(s) after patch'.format(len(issues)))
            stats.api.increment('analysis.issues.after', len(issues))

            # Mark newly found issues
            if settings.publication == Publication.BEFORE_AFTER:
                for issue in issues:
                    issue.is_new = issue not in before_patch

        # Avoid duplicates
        issues = set(issues)

        if not issues:
            logger.info('No issues, stopping there.')
            self.index(revision, state='done', issues=0)
            return

        # Publish patches on Taskcluster
        # or write locally for local development
        for patch in revision.improvement_patches:
            if settings.taskcluster.local:
                patch.write()
            else:
                patch.publish(self.queue_service)

        # Report issues publication stats
        nb_issues = len(issues)
        nb_publishable = len([i for i in issues if i.is_publishable()])
        self.index(revision, state='analyzed', issues=nb_issues, issues_publishable=nb_publishable)
        stats.api.increment('analysis.issues.publishable', nb_publishable)

        # Publish reports about these issues
        with stats.api.timer('runtime.reports'):
            for reporter in self.reporters.values():
                reporter.publish(issues, revision)

        self.index(revision, state='done', issues=nb_issues, issues_publishable=nb_publishable)

    def detect_issues(self, analyzers, revision):
        '''
        Detect issues for this revision
        '''
        issues = []
        for analyzer_class in analyzers:
            # Build analyzer
            logger.info('Run {}'.format(analyzer_class.__name__))
            analyzer = analyzer_class()

            # Run analyzer on revision and store generated issues
            issues += analyzer.run(revision)

        return issues

    def index(self, revision, **kwargs):
        '''
        Index current task on Taskcluster index
        '''
        assert isinstance(revision, Revision)

        if settings.taskcluster.local:
            logger.info('Skipping taskcluster indexing', rev=str(revision), **kwargs)
            return

        # Build payload
        payload = revision.as_dict()
        payload.update(kwargs)

        # Always add the indexing
        now = datetime.utcnow()
        payload['indexed'] = now.strftime(TASKCLUSTER_DATE_FORMAT)

        # Index for all required namespaces
        for name in revision.namespaces:
            namespace = TASKCLUSTER_NAMESPACE.format(channel=settings.app_channel, name=name)
            self.index_service.insertTask(
                namespace,
                {
                    'taskId': settings.taskcluster.task_id,
                    'rank': 0,
                    'data': payload,
                    'expires': (now + timedelta(days=TASKCLUSTER_INDEX_TTL)).strftime(TASKCLUSTER_DATE_FORMAT),
                }
            )
