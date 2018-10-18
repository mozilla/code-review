# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import subprocess

from cli_common.command import run_check
from cli_common.log import get_logger
from static_analysis_bot import INFER
from static_analysis_bot import AnalysisException
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.infer import AndroidConfig
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## infer error

- **Message**: {message}
- **Location**: {location}
- **In patch**: {in_patch}
- **Infer check**: {check}
- **Publishable **: {publishable}
- **Is new**: {is_new}

```
{body}
```
'''

INFER_SETUP_CMD = [
    'gecko-env',
    './mach', 'artifact', 'toolchain',
    '--from-build', 'linux64-infer'
]


class Infer(object):
    '''
    Infer runner
    '''
    def __init__(self, validate_checks=True):
        self.binary = os.path.join(
            os.environ['MOZBUILD_STATE_PATH'],
            'infer', 'infer', 'bin', 'infer',
        )
        assert os.path.exists(self.binary), \
            'Missing infer in {}'.format(self.binary)

    @stats.api.timed('runtime.infer')
    def run(self, revision):
        '''
        Run modified files with specified checks through infer
        using threaded workers (communicate through queues)
        Output a list of InferIssue
        '''
        assert isinstance(revision, Revision)
        self.revision = revision

        with AndroidConfig():
            # Mach pre-setup with mozconfig
            logger.info('Mach configure for infer...')
            run_check(['gecko-env', './mach', 'configure'],
                      cwd=settings.repo_dir)

            # Run all files in a single command
            # through mach static-analysis
            cmd = [
                'gecko-env',
                './mach', '--log-no-times', 'static-analysis', 'check-java'
            ] + list(revision.files)
            logger.info('Running static-analysis', cmd=' '.join(cmd))

            # Run command
            try:
                infer_output = subprocess.check_output(cmd, cwd=settings.repo_dir)
            except subprocess.CalledProcessError as e:
                raise AnalysisException('infer', 'Mach static analysis failed: {}'.format(e.output))

        report_file = os.path.join(settings.repo_dir, 'infer-out', 'report.json')
        infer_output = json.load(open(report_file))

        # Dump raw infer output as a Taskcluster artifact (for debugging)
        infer_output_path = os.path.join(
            settings.taskcluster.results_dir,
            '{}-infer.txt'.format(repr(revision)),
        )
        with open(infer_output_path, 'w') as f:
            f.write(json.dumps(infer_output, indent=2))
        issues = self.parse_issues(infer_output, revision)

        # Report stats for these issues
        stats.report_issues('infer', issues)
        return issues

    def parse_issues(self, infer_output, revision):
        '''
        Parse infer output into structured issues
        '''
        if not infer_output:
            logger.info('Infer could not generate any output.')
            return []

        # check if json is empty
        nb_warnings = len(infer_output)
        if not nb_warnings:
            logger.info('Mach static analysis check-java did not find any issue')
            return []
        logger.info('Mach static analysis found some issues', nb=nb_warnings)
        return [InferIssue(issue, revision) for issue in infer_output]


class InferIssue(Issue):
    '''
    An issue reported by infer
    '''
    ANALYZER = INFER

    def __init__(self, entry, revision):
        assert isinstance(entry, dict)
        assert not settings.repo_dir.endswith('/')
        self.revision = revision
        self.path = entry['file']
        self.line = entry['line']
        self.column = entry['column']
        self.bug_type = entry['bug_type']
        self.kind = entry['kind']
        self.message = entry['qualifier']
        self.body = None
        self.nb_lines = 1

    def __str__(self):
        return '[{}] {} {}:{}'.format(self.bug_type, self.path,
                                      self.line, self.column)

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'bug_type': self.bug_type,
            'kind': self.kind,
            'column': self.column,
        }

    def is_problem(self):
        return self.kind in ('ERROR')

    def validates(self):
        '''
        Publish infer issues all the time
        '''
        return True

    def as_text(self):
        '''
        Build the text body published on reporters
        '''
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        body = '{}: {} [infer: {}]'.format(self.kind, message, self.bug_type)
        if self.body:
            self.body += '\n{}'.format(body)
        return body

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            check=self.bug_type,
            message=self.message,
            location='{}:{}:{}'.format(self.path, self.line, self.column),
            body=self.body,
            in_patch='yes' if self.revision.contains(self) else 'no',
            publishable='yes' if self.is_publishable() else 'no',
            is_new='yes' if self.is_new else 'no'
        )

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'infer',
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'column': self.column,
            'bug_type': self.bug_type,
            'kind': self.kind,
            'message': self.message,
            'body': self.body,
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
        }
