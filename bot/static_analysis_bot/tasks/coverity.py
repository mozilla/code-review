# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common.log import get_logger
from cli_common.phabricator import LintResult
from static_analysis_bot import COVERITY
from static_analysis_bot import AnalysisException
from static_analysis_bot import Issue
from static_analysis_bot import Reliability
from static_analysis_bot.config import settings
from static_analysis_bot.tasks.base import AnalysisTask

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## coverity error

- **Message**: {message}
- **Location**: {location}
- **Coverity check**: {check}
- **Publishable **: {publishable}
- **Is Clang Error**: {is_clang_error}
- **Is Local**: {is_local}
- **Reliability**: {reliability}

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

    def __init__(self, revision, issue, file_path=None):
        self.revision = revision
        self.reliability = Reliability.Unknown

        if file_path is None:
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
            self.state_on_server = issue['stateOnServer']

            if settings.cov_full_stack:
                self.message += ISSUE_RELATION
                # Embed all events into message
                for event in issue['events']:
                    self.message += ISSUE_ELEMENT_IN_STACK.format(
                        file_path=event['strippedFilePathname'],
                        line_number=event['lineNumber'],
                        path_type=event['eventTag'],
                        description=event['eventDescription'])
        else:
            # This issue came from try worker
            self.path = file_path
            self.reliability = Reliability(issue['reliability'])
            self.line = issue['line']
            self.bug_type = issue['extra']['category']
            self.kind = issue['flag']
            self.message = issue['message']

            self.state_on_server = issue['extra']['stateOnServer']
            if settings.cov_full_stack:
                self.message += ISSUE_RELATION
                # Embed all events into message
                if 'stack' in issue['extra']:
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

    def is_publishable(self):
        '''
        We don't use the default `is_publishable` implementation from `Issue`
        because for CoverityIssue we don't apply the same logic to filter issues
        as we do with the rest of our Analyzers, for IN_PATCH or BEFORE_AFTER methods,
        since Coverity performs most of the checks on the servers and provides us a
        snapshot with the checks that can be filtered only by the is_local function.
        Coverity also has the ability to forward clang errors but we don't want to forward
        these errors to the review.
        '''
        return not self.is_clang_error() and self.is_local()

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
        return self.is_local()

    def as_text(self):
        '''
        Build the text body published on reporters
        '''
        # If there is the reliability index use it
        return f'Checker reliability (false positive risk) is {self.reliability.value}.\n{self.message}' \
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
        message = f'Checker reliability (false positive risk) is {self.reliability.value}.\n{self.message}' \
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
