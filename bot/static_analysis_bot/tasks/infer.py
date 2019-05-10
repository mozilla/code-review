# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common.log import get_logger
from cli_common.phabricator import LintResult
from static_analysis_bot import INFER
from static_analysis_bot import Issue
from static_analysis_bot.tasks.base import AnalysisTask

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


class InferIssue(Issue):
    '''
    An issue reported by infer
    '''
    ANALYZER = INFER

    def __init__(self, entry, revision):
        assert isinstance(entry, dict)
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

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        return LintResult(
            name=self.message,
            code='infer.{}'.format(self.bug_type),
            severity=self.kind,
            path=self.path,
            line=self.line,
            char=self.column,
            description=self.body,
        )


class InferTask(AnalysisTask):
    '''
    Support remote Infer analyzer
    '''
    artifacts = [
        'public/code-review/infer.json',
    ]

    def parse_issues(self, artifacts, revision):
        '''
        Parse issues from a direct Infer JSON report
        '''
        assert isinstance(artifacts, dict)
        return [
            InferIssue(issue, revision)
            for issues in artifacts.values()
            for issue in issues
        ]
