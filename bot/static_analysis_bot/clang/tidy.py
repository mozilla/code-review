# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import fnmatch
import os
import re
import subprocess

from cli_common.log import get_logger
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import CONFIG_URL
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

REGEX_HEADER = re.compile(r'^(.+):(\d+):(\d+): (warning|error|note): ([^\[\]\n]+)(?: \[([\.\w-]+)\])?$', re.MULTILINE)
REGEX_FOOTER = re.compile(r'^(Warning: [\.\w-]+ in .+:)|(Suppressed \d+ warnings)|(\d+ warnings? and \d+ errors? generated.)|(Error while processing)', re.MULTILINE)  # noqa
REGEX_HAS_WARNINGS = re.compile(r'^(\d+) warnings|errors present.$', re.MULTILINE)


ISSUE_MARKDOWN = '''
## clang-tidy {type}

- **Message**: {message}
- **Location**: {location}
- **In patch**: {in_patch}
- **Clang check**: {check}
- **Publishable check**: {publishable_check}
- **Third Party**: {third_party}
- **Expanded Macro**: {expanded_macro}
- **Publishable **: {publishable}
- **Is new**: {is_new}

```
{body}
```

{notes}
'''

ISSUE_NOTE_MARKDOWN = '''
- **Note**: {message}
- **Location**: {location}

```
{body}
```
'''

CLANG_MACRO_DETECTION = re.compile(r'^expanded from macro')

CLANG_SETUP_CMD = [
    'gecko-env',
    './mach', 'artifact', 'toolchain',
    '--from-build', 'linux64-clang-tidy'
]


class ClangTidy(object):
    '''
    Clang Tidy Parallel runner
    Inspired by run-clang-tidy.py
    '''
    def __init__(self, validate_checks=True):
        self.binary = os.path.join(
            os.environ['MOZBUILD_STATE_PATH'],
            'clang-tools', 'clang', 'bin', 'clang-tidy',
        )
        assert os.path.exists(self.binary), \
            'Missing clang-tidy in {}'.format(self.binary)

        # Verify that all specified clang-tidy checks still exist
        if validate_checks:
            for missing in self.list_missing_checks():
                logger.error('Specified clang-tidy check "{}" not found.'.format(missing))

    @stats.api.timed('runtime.clang-tidy')
    def run(self, revision):
        '''
        Run modified files with specified checks through clang-tidy
        using threaded workers (communicate through queues)
        Output a list of ClangTidyIssue
        '''
        assert isinstance(revision, Revision)
        self.revision = revision

        # Run all files in a single command
        # through mach static-analysis
        cmd = [
            'gecko-env',
            './mach', '--log-no-times', 'static-analysis', 'check',

            # Limit warnings to current files
            '--header-filter={}'.format('|'.join(
                os.path.basename(filename)
                for filename in revision.files
            )),

            '--checks={}'.format(','.join(c['name'] for c in settings.clang_checkers)),
        ] + list(revision.files)
        logger.info('Running static-analysis', cmd=' '.join(cmd))

        # Run command
        try:
            clang_output = subprocess.check_output(cmd, cwd=settings.repo_dir)
        except subprocess.CalledProcessError as e:
            logger.error('Mach static analysis failed: {}'.format(e.output))
            raise

        clang_output = clang_output.decode('utf-8')

        # Dump raw clang-tidy output as a Taskcluster artifact (for debugging)
        clang_output_path = os.path.join(
            settings.taskcluster_results_dir,
            '{}-clang-tidy.txt'.format(repr(revision)),
        )
        with open(clang_output_path, 'w') as f:
            f.write(clang_output)

        issues = self.parse_issues(clang_output, revision)

        # Report stats for these issues
        stats.report_issues('clang-tidy', issues)

        return issues

    def parse_issues(self, clang_output, revision):
        '''
        Parse clang-tidy output into structured issues
        '''
        # Detect end of file warnings count
        # When an invalid file is used, this line does not appear
        has_warnings = REGEX_HAS_WARNINGS.search(clang_output)
        if has_warnings is None:
            logger.info('Empty clang output, skipping analysis.')
            return []
        nb_warnings = int(has_warnings.group(1))
        if nb_warnings == 0:
            logger.info('Mach static analysis did not find any issue')
            return []
        logger.info('Mach static analysis found some issues', nb=nb_warnings)

        # Sort headers by positions
        headers = sorted(
            REGEX_HEADER.finditer(clang_output),
            key=lambda h: h.start()
        )
        if not headers:
            raise Exception('No clang-tidy header was found even though a clang output was provided')

        def _remove_footer(start_pos, end_pos):
            '''
            Build an issue body from clang-tidy output
            and stops when an extra paylaod is detected (footer)
            '''
            assert isinstance(start_pos, int)
            assert isinstance(end_pos, int)
            body = clang_output[start_pos:end_pos]
            footer = REGEX_FOOTER.search(body)
            if footer is None:
                return body
            return body[:footer.start()-1]

        issues = []
        for i, header in enumerate(headers):
            issue = ClangTidyIssue(header.groups(), revision)

            # Get next header
            if i+1 < len(headers):
                # Parse body until next header
                next_header = headers[i+1]
                issue.body = _remove_footer(header.end(), next_header.start() - 1)
            else:
                # Limit last element to 3 lines to avoid parsing extra metadatas
                issue.body = _remove_footer(header.end(), header.end() + 3)

            if issue.is_problem():
                # Save problem to append notes
                # Skip diagnostic errors, but warn through Sentry
                if issue.check == 'clang-diagnostic-error':
                    logger.error('Encountered a clang-diagnostic-error: {}'.format(issue))
                else:
                    issues.append(issue)
                    mode = issue.is_third_party() and '3rd party' or 'in-tree'
                    logger.info('Found {} code issue {}'.format(mode, issue))

            elif issues:
                # Link notes to last problem
                issues[-1].notes.append(issue)

        return issues

    def list_available_checks(self):
        '''
        Build the set of all available checks that the local clang-tidy offers
        '''
        cmd = [
            self.binary,
            '-list-checks',
            '-checks=*'
        ]
        clang_output = subprocess.check_output(cmd).decode('utf-8')
        available_checks = set(line.strip() for line in clang_output.split('\n')[1:])
        return available_checks

    def list_missing_checks(self):
        '''
        List all the clang-tidy missing checks according to config
        '''
        available_checks = self.list_available_checks()
        if len(settings.clang_checkers) > 0:
            logger.info('Available clang-tidy checks:\n\t{}'.format('\n\t'.join(available_checks)))
        else:
            logger.error('Firefox clang-tidy configuration {} should specify > 0 clang_checkers'.format(CONFIG_URL))

        return [
            check['name']
            for check in settings.clang_checkers
            if not len(fnmatch.filter(available_checks, check['name'])) > 0
            and check['name'] != '-*'  # Special check -* is not listed by clang-tidy
        ]


class ClangTidyIssue(Issue):
    '''
    An issue reported by clang-tidy
    '''
    def __init__(self, header_data, revision):
        assert isinstance(header_data, tuple)
        assert len(header_data) == 6
        assert not settings.repo_dir.endswith('/')
        self.revision = revision
        self.path, self.line, self.char, self.type, self.message, self.check = header_data  # noqa
        if self.path.startswith(settings.repo_dir):
            self.path = self.path[len(settings.repo_dir)+1:]  # skip heading /
        self.line = int(self.line)
        self.nb_lines = 1  # Only 1 line affected on clang-tidy
        self.char = int(self.char)
        self.body = None
        self.notes = []

    def __str__(self):
        return '[{}] {} {} {}:{}'.format(self.type, self.check, self.path, self.line, self.char)

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'type': self.type,
            'check': self.check,
            'char': self.char,
        }

    def is_problem(self):
        return self.type in ('warning', 'error')

    def validates(self):
        '''
        Publish clang-tidy issues when:
        * not a third party code
        * check is marked as publishable
        * is not from an expanded macro
        '''
        return self.has_publishable_check() \
            and not self.is_third_party() \
            and not self.is_expanded_macro()

    def is_expanded_macro(self):
        '''
        Is the issue only found in an expanded macro ?
        '''
        if not self.notes:
            return False

        # Only consider first note
        note = self.notes[0]
        return CLANG_MACRO_DETECTION.match(note.message) is not None

    def has_publishable_check(self):
        '''
        Is this issue using a publishable check ?
        '''
        # Never publish a note (no check attached)
        if not self.is_problem():
            return False

        return settings.is_publishable_check(self.check)

    def as_text(self):
        '''
        Build the text body published on reporters
        '''
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        body = '{}: {} [clang-tidy: {}]'.format(
            self.type.capitalize(),
            message,
            self.check,
        )

        # Always add body as it's been cleaned up
        if self.body:
            body += '\n{}'.format(self.body)

        return body

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            type=self.type,
            message=self.message,
            location='{}:{}:{}'.format(self.path, self.line, self.char),
            body=self.body,
            check=self.check,
            in_patch='yes' if self.revision.contains(self) else 'no',
            third_party='yes' if self.is_third_party() else 'no',
            publishable_check='yes' if self.has_publishable_check() else 'no',
            publishable='yes' if self.is_publishable() else 'no',
            expanded_macro='yes' if self.is_expanded_macro() else 'no',
            is_new='yes' if self.is_new else 'no',
            notes='\n'.join([
                ISSUE_NOTE_MARKDOWN.format(
                    message=n.message,
                    location='{}:{}:{}'.format(n.path, n.line, n.char),
                    body=n.body,
                ) for n in self.notes
            ]),
        )

    def as_diff(self):
        '''
        No diff available
        '''

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'clang-tidy',
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'char': self.char,
            'check': self.check,
            'type': self.type,
            'message': self.message,
            'body': self.body,
            'notes': [note.as_dict() for note in self.notes],
            'validation': {
                'publishable_check': self.has_publishable_check(),
                'third_party': self.is_third_party(),
                'is_expanded_macro': self.is_expanded_macro(),
            },
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
        }
