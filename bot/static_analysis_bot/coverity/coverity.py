# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import shutil
import subprocess

from cli_common.command import run_check
from cli_common.log import get_logger
from static_analysis_bot import COVERITY
from static_analysis_bot import AnalysisException
from static_analysis_bot import DefaultAnalyzer
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## coverity error

- **Message**: {message}
- **Location**: {location}
- **In patch**: {in_patch}
- **Coverity check**: {check}
- **Publishable **: {publishable}
- **Is new**: {is_new}

```
{body}
```
'''

ISSUE_ELEMENT_IN_STACK = '''
- //{file_path}:{line_number}//:
-- `{path_type}: {description}`.
'''

ISSUE_RELATION = '''
The path that leads to this defect is:
'''


class Coverity(DefaultAnalyzer):
    '''
    Coverity runner
    '''
    def __init__(self, validate_checks=True):
        # Ensure that we have all what we need into settings
        assert settings.cov_package_name, 'Missing secret COVERITY_CONFIG:package_name'
        assert settings.cov_package_ver, 'Missing secret COVERITY_CONFIG:package_ver'

        self.cov_state_path = os.path.join(os.environ['MOZBUILD_STATE_PATH'],
                                           'coverity')
        self.cov_path = os.path.join(self.cov_state_path,
                                     settings.cov_package_name)
        self.cov_run_desktop = os.path.join(self.cov_path, 'bin', 'cov-run-desktop')
        self.cov_translate = os.path.join(self.cov_path, 'bin', 'cov-translate')
        self.cov_configure = os.path.join(self.cov_path, 'bin', 'cov-configure')
        self.cov_work_path = os.path.join(self.cov_state_path, 'data-coverity')
        self.cov_idir_path = os.path.join(self.cov_work_path, settings.cov_package_ver, 'idir')

        assert os.path.exists(self.cov_path), \
            'Missing Coverity in {}'.format(self.cov_path)

    def get_files_with_commands(self):
        '''
        Returns an array of dictionaries having file_path with build command
        '''

        compile_db = json.load(open(self.compile_commands_path, 'r'))

        commands_list = []

        for rev_file in self.revision.files:
            # It must be a C/C++ file
            _, ext = os.path.splitext(rev_file)

            if ext.lower() not in settings.cpp_extensions:
                continue
            file_with_abspath = os.path.join(settings.repo_dir, rev_file)
            for f in compile_db:
                # Found for a file that we are looking
                if file_with_abspath == f['file']:
                    commands_list.append(f)

        return commands_list

    @stats.api.timed('runtime.coverity')
    def run(self, revision):
        '''
        Run coverity
        '''
        assert isinstance(revision, Revision)
        self.revision = revision

        # Based on our previous configs we should already have generated compile_commands.json
        self.compile_commands_path = os.path.join(settings.repo_dir, 'obj-x86_64-pc-linux-gnu', 'compile_commands.json')

        assert os.path.exists(self.compile_commands_path), \
            'Missing Coverity in {}'.format(self.compile_commands_path)

        logger.info('Building command files from compile_commands.json')

        # Retrieve the revision files with build commands associated
        commands_list = self.get_files_with_commands()
        assert commands_list is not [], 'Commands List is empty'
        logger.info('Built commands for {} files'.format(len(commands_list)))

        if len(commands_list) == 0:
            logger.info('Coverity didn\'t find any compilation units to use.')
            return []

        cmd = ['gecko-env', self.cov_run_desktop, '--setup']
        logger.info('Running Coverity Setup', cmd=cmd)
        try:
            run_check(cmd, cwd=self.cov_path)
        except subprocess.CalledProcessError as e:
            raise AnalysisException('coverity', 'Coverity Setup failed: {}'.format(e.output))

        cmd = ['gecko-env', self.cov_configure, '--clang']
        logger.info('Running Coverity Configure', cmd=cmd)
        try:
            run_check(cmd, cwd=self.cov_path)
        except subprocess.CalledProcessError as e:
            raise AnalysisException('coverity', 'Coverity Configure failed: {}'.format(e.output))

        # For each element in commands_list run `cov-translate`
        for element in commands_list:
            cmd = [
                'gecko-env', self.cov_translate, '--dir', self.cov_idir_path,
                element['command']
            ]
            logger.info('Running Coverity Tranlate', cmd=cmd)
            try:
                run_check(cmd, cwd=element['directory'])
            except subprocess.CalledProcessError as e:
                raise AnalysisException('coverity', 'Coverity Translate failed: {}'.format(e.output))

        # Once the capture is performed we need to do the actual Coverity Desktop analysis
        cmd = [
            'gecko-env', self.cov_run_desktop, '--json-output-v6',
            'cov-results.json', '--strip-path', settings.repo_dir
        ]
        cmd += [element['file'] for element in commands_list]
        logger.info('Running Coverity Analysis', cmd=cmd)
        try:
            run_check(cmd, cwd=self.cov_state_path)
        except subprocess.CalledProcessError as e:
            raise AnalysisException('coverity', 'Coverity Analysis failed: {}'.format(e.output))

        # Write the results.json to the artifact directory to have it later on for debug
        coverity_results_path = os.path.join(self.cov_state_path, 'cov-results.json')
        coverity_results_path_on_tc = os.path.join(settings.taskcluster.results_dir, 'cov-results.json')

        shutil.copyfile(coverity_results_path, coverity_results_path_on_tc)

        # Parsing the issues from coverity_results_path
        logger.info('Parsing Coverity issues')
        return self.return_issues(coverity_results_path, revision)

    def return_issues(self, coverity_results_path, revision):
        '''
        Parse Coverity json into structured issues
        '''
        if not os.path.isfile(coverity_results_path):
            raise AnalysisException(
                'coverity',
                'Coverity Analysis did not generate an analysis report.')

        with open(coverity_results_path) as f:
            result = json.load(f)

            if 'issues' not in result:
                logger.info('Coverity did not find any issues')
                return []

            return [CoverityIssue(issue, revision) for issue in result['issues']]

    def can_run_before_patch(self):
        '''
        Coverity should run only once, after the patch is applied.
        '''
        return False


class CoverityIssue(Issue):
    '''
    An issue reported by coverity
    '''
    ANALYZER = COVERITY

    def __init__(self, issue, revision):
        assert not settings.repo_dir.endswith('/')
        self.revision = revision
        # We look only for main event
        event_path = next((event for event in issue['events'] if event['main'] is True), None)

        if event_path is None:
            raise AnalysisException(
                'coverity',
                'Coverity Analysis did not find main event for mergeKey {}'.format(issue['mergeKey']))

        checker_properties = issue['checkerProperties']
        # Strip the leading slash
        self.path = issue['strippedMainEventFilePathname'].strip('/')
        self.line = issue['mainEventLineNumber']
        self.bug_type = checker_properties['category']
        self.kind = issue['checkerName']
        self.message = event_path['eventDescription']
        self.body = None
        self.nb_lines = 1

        if settings.cov_full_stack:
            self.message += ISSUE_RELATION
            # Embed all events into message
            for event in issue['events']:
                self.message += ISSUE_ELEMENT_IN_STACK.format(
                    file_path=event['strippedFilePathname'],
                    line_number=event['lineNumber'],
                    path_type=event['eventTag'],
                    description=event['eventDescription'])

    def __str__(self):
        return '[{}] {} {}'.format(self.kind, self.path, self.line)

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'bug_type': self.bug_type,
            'kind': self.kind,
            'line': self.line,
        }

    def is_problem(self):
        return True

    def validates(self):
        '''
        Publish Coverity issues all the time
        '''
        return True

    def as_text(self):
        '''
        Build the text body published on reporters
        '''
        return self.message

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            check=self.kind,
            message=self.message,
            location='{}:{}'.format(self.path, self.line),
            body=self.body,
            in_patch='yes',
            publishable='yes',
            is_new='yes'
        )

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'Coverity',
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'bug_type': self.bug_type,
            'kind': self.kind,
            'message': self.message,
            'body': self.body,
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': True,
        }
