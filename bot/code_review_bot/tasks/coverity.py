# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog
from libmozdata.phabricator import LintResult

from static_analysis_bot import COVERITY
from static_analysis_bot import Issue
from static_analysis_bot import Reliability
from static_analysis_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = '''
## coverity error

- **Message**: {message}
- **Location**: {location}
- **Coverity check**: {check}
- **Publishable **: {publishable}
- **Is Clang Error**: {is_clang_error}
- **Is Local**: {is_local}
- **Reliability**: {reliability} (false positive risk)

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


class CoverityIssue(Issue):
    '''
    An issue reported by coverity
    '''
    ANALYZER = COVERITY

    def __init__(self, revision, issue, file_path):
        self.revision = revision
        self.path = file_path
        self.reliability = Reliability(issue['reliability'])
        self.line = issue['line']
        self.bug_type = issue['extra']['category']
        self.kind = issue['flag']
        self.message = issue['message']

        self.state_on_server = issue['extra']['stateOnServer']
        # If we have `stack` in the `try` result then embed it in the message.
        if 'stack' in issue['extra']:
            self.message += ISSUE_RELATION
            stack = issue['extra']['stack']
            for event in stack:
                self.message += ISSUE_ELEMENT_IN_STACK.format(
                    file_path=event['file_path'],
                    line_number=event['line_number'],
                    path_type=event['path_type'],
                    description=event['description'])

        self.body = None
        self.nb_lines = 1

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

    def is_clang_error(self):
        '''
        Determine if the current issue is a translation unit error forwarded by Clang
        '''
        return 'RW.CLANG' in self.kind

    def is_local(self):
        '''
        The given coverity issue should be only locally stored and not in the
        remote snapshot
        '''
        # According to Coverity manual:
        # presentInReferenceSnapshot - True if the issue is present in the reference
        # snapshot specified in the cov-run-desktop command, false if not.
        return self.state_on_server is not None and 'presentInReferenceSnapshot' in self.state_on_server \
            and self.state_on_server['presentInReferenceSnapshot'] is False

    def validates(self):
        '''
        Publish only local Coverity issues
        '''
        return self.is_local() and not self.is_clang_error()

    def as_text(self):
        '''
        Build the text body published on reporters
        '''
        # If there is the reliability index use it
        return f'Checker reliability is {self.reliability.value}, meaning that the false positive ratio is {self.reliability.invert}.\n{self.message}' \
            if self.reliability != Reliability.Unknown \
            else self.message

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            check=self.kind,
            message=self.message,
            location='{}:{}'.format(self.path, self.line),
            body=self.body,
            publishable=self.is_publishable() and 'yes' or 'no',
            is_local=self.is_local() and 'yes' or 'no',
            reliability=self.reliability.value,
            is_clang_error=self.is_clang_error() and 'yes' or 'no',
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
            'reliability': self.reliability.value,
            'message': self.message,
            'body': self.body,
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'is_local': self.is_local(),
            'validates': self.validates(),
            'validation': {
                'is_local': self.is_local(),
                'is_clang_error': self.is_clang_error(),
            },
            'publishable': self.is_publishable(),
        }

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        # If there is the reliability index use it
        message = f'Checker reliability is {self.reliability.value}, meaning that the false positive ratio is {self.reliability.invert}.\n{self.message}'\
            if self.reliability != Reliability.Unknown \
            else self.message

        return LintResult(
            name=message,
            code='coverity.{}'.format(self.kind),
            severity='error',
            path=self.path,
            line=self.line,
            description=self.body,
        )


class CoverityTask(AnalysisTask):
    '''
    Support remote Coverity analyzer
    '''
    artifacts = [
        'public/code-review/coverity.json',
    ]

    def parse_issues(self, artifacts, revision):
        '''
        Parse issues from a pre-translated Coverity report
        '''
        assert isinstance(artifacts, dict)
        return [
            CoverityIssue(
                revision,
                issue=warning,
                file_path=self.clean_path(path)
            )
            for artifact in artifacts.values()
            for path, items in artifact['files'].items()
            for warning in items['warnings']
        ]
