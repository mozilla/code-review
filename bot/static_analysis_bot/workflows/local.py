# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import fcntl
import os
import shutil
import time

import hglib

from cli_common.command import run_check
from cli_common.log import get_logger
from static_analysis_bot import CLANG_FORMAT
from static_analysis_bot import CLANG_TIDY
from static_analysis_bot import COVERAGE
from static_analysis_bot import COVERITY
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
from static_analysis_bot.coverage import Coverage
from static_analysis_bot.coverity import setup as setup_coverity
from static_analysis_bot.coverity.coverity import Coverity
from static_analysis_bot.infer import setup as setup_infer
from static_analysis_bot.infer.infer import Infer
from static_analysis_bot.lint import MozLint

logger = get_logger(__name__)


class LocalWorkflow(object):
    '''
    Run analyers in current task
    '''
    def __init__(self, parent, analyzers, index_service):
        self.parent = parent
        assert isinstance(analyzers, list)
        assert len(analyzers) > 0, \
            'No analyzers specified, will not run.'
        self.analyzers = analyzers
        assert 'MOZCONFIG' in os.environ, \
            'Missing MOZCONFIG in environment'

        # Use TC services client
        self.index_service = index_service

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

        def _log_process(output, name):
            # Read and display every line
            out = output.read()
            if out is None:
                return
            text = filter(None, out.decode('utf-8').splitlines())
            for line in text:
                logger.info('{}: {}'.format(name, line))

        # Start process
        start = time.time()
        proc = hglib.util.popen(cmd)

        # Set process outputs as non blocking
        for output in (proc.stdout, proc.stderr):
            fcntl.fcntl(
                output.fileno(),
                fcntl.F_SETFL,
                fcntl.fcntl(output, fcntl.F_GETFL) | os.O_NONBLOCK,
            )

        while proc.poll() is None:
            _log_process(proc.stdout, 'clone')
            _log_process(proc.stderr, 'clone (err)')
            time.sleep(1)

        out, err = proc.communicate()
        if proc.returncode != 0:
            raise Exception('Mercurial clone failed with exit code {}'.format(proc.returncode))
        logger.info('Clone finished', time=(time.time() - start), out=out, err=err)

        # Open new hg client
        client = hglib.open(settings.repo_dir)

        # Attach logger
        client.setcbout(lambda msg: logger.info('Mercurial out={}'.format(msg.decode('utf-8'))))
        client.setcberr(lambda msg: logger.info('Mercurial err={}'.format(msg.decode('utf-8'))))

        # Store MC top revision after robustcheckout
        self.top_revision = client.log('reverse(public())', limit=1)[0].node
        logger.info('Mozilla unified top revision', revision=self.top_revision)

        return client

    def run(self, revision):
        '''
        Run the local static analysis workflow:
         * Pull revision from review
         * Checkout revision
         * Run static analyzers
        '''
        analyzers = []

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
                self.parent.index(revision, state='cloned')

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
                self.do_build_setup()

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

                # Run Coverity Scan
                if COVERITY in self.analyzers:
                    logger.info('Setup Taskcluster coverity build...')
                    setup_coverity(self.index_service)
                    analyzers.append(Coverity)
                else:
                    logger.info('Skip Coverity')

                if COVERAGE in self.analyzers:
                    analyzers.append(Coverage)
                else:
                    logger.info('Skip coverage analysis')

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

        self.parent.index(revision, state='analyzing')
        with stats.api.timer('runtime.issues'):
            # Detect initial issues
            if settings.publication == Publication.BEFORE_AFTER:
                before_patch = self.detect_issues(analyzers, revision, True)
                logger.info('Detected {} issue(s) before patch'.format(len(before_patch)))
                stats.api.increment('analysis.issues.before', len(before_patch))
                revision.reset()

            # Apply patch
            revision.apply(self.hg)

            if settings.publication == Publication.BEFORE_AFTER and revision.has_clang_files \
                    and (revision.has_clang_header_files or revision.has_idl_files):
                self.do_build_setup()

            # Detect new issues
            issues = self.detect_issues(analyzers, revision)
            logger.info('Detected {} issue(s) after patch'.format(len(issues)))
            stats.api.increment('analysis.issues.after', len(issues))

            # Mark newly found issues
            if settings.publication == Publication.BEFORE_AFTER:
                for issue in issues:
                    issue.is_new = issue not in before_patch

        # Avoid duplicates
        # but still output a list to be compatible with LocalWorkflow
        return list(set(issues))

    @stats.api.timer('runtime.mach.setup')
    def do_build_setup(self):
        # Mach pre-setup with mozconfig
        try:
            logger.info('Mach delete any existing obj dir')
            obj_dir = os.path.join(settings.repo_dir, 'obj-x86_64-pc-linux-gnu')
            if (os.path.exists(obj_dir)):
                shutil.rmtree(obj_dir)

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

    def detect_issues(self, analyzers, revision, is_before=False):
        '''
        Detect issues for this revision
        '''
        issues = []
        for analyzer_class in analyzers:
            # Build analyzer
            analyzer = analyzer_class()
            analyzer_issues = []
            try:
                if is_before:
                    if analyzer.can_run_before_patch():
                        # Run analyzer on revision and store generated issues
                        logger.info('Run {} with no patch applied'.format(analyzer_class.__name__))
                        analyzer_issues = analyzer.run(revision)
                    else:
                        logger.info('Skipped running {} with no patch applied'.format(analyzer_class.__name__))
                        continue
                else:
                    logger.info('Run {}'.format(analyzer_class.__name__))
                    analyzer_issues = analyzer.run(revision)

            except AnalysisException as ex:
                # Log the error to Sentry
                logger.error('Analyzer thrown exceptions during runtime', analyzer=analyzer_class.__name__, exception=ex)

            finally:
                # Clean up any uncommitted changes left behind by this analyzer.
                self.hg.revert(settings.repo_dir.encode('utf-8'), all=True)
                logger.info('Reverted all uncommitted changes in repo', rev=self.hg.identify())

                # Compute line hashes now before anything else changes the code.
                for issue in analyzer_issues:
                    issue.build_lines_hash()

                issues += analyzer_issues

        return issues
