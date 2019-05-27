# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from libmozdata.phabricator import LintResult

from cli_common.log import get_logger
from static_analysis_bot import CLANG_TIDY
from static_analysis_bot import Issue
from static_analysis_bot import Reliability
from static_analysis_bot.config import settings
from static_analysis_bot.tasks.base import AnalysisTask

logger = get_logger(__name__)


ISSUE_MARKDOWN = '''
## clang-tidy {level}

- **Message**: {message}
- **Location**: {location}
- **In patch**: {in_patch}
- **Clang check**: {check}
- **Publishable check**: {publishable_check}
- **Third Party**: {third_party}
- **Expanded Macro**: {expanded_macro}
- **Publishable **: {publishable}
- **Is new**: {is_new}
- **Checker reliability **: {reliability} (false positive risk)

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


class ClangTidyIssue(Issue):
    '''
    An issue reported by clang-tidy
    '''
    ANALYZER = CLANG_TIDY

    def __init__(self, revision, path, line, char, check, message, level='warning', reliability=Reliability.Unknown):
        assert isinstance(reliability, Reliability)

        self.revision = revision
        self.path = path
        self.line = int(line)
        self.nb_lines = 1  # Only 1 line affected on clang-tidy
        self.char = int(char)
        self.check = check
        self.message = message
        self.body = None
        self.notes = []
        self.level = level
        self.reason = None
        self.reliability = reliability
        check = settings.get_clang_check(self.check)
        if check is not None:
            self.reason = check.get('reason')

    def __str__(self):
        return '[{}] {} {} {}:{}'.format(self.level, self.check, self.path, self.line, self.char)

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'level': self.level,
            'check': self.check,
            'char': self.char,
        }

    def is_problem(self):
        return self.level in ('warning', 'error')

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
            self.level.capitalize(),
            message,
            self.check,
        )

        # Always add body as it's been cleaned up
        if self.body:
            body += '\n```\n{}\n```'.format(self.body)
        if self.reason:
            body += '\n{}'.format(self.reason)
        # Also add the reliability of the checker
        if self.reliability != Reliability.Unknown:
            body += '\nChecker reliability is {} (false positive risk).'.format(self.reliability.value)
        return body

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            level=self.level,
            message=self.message,
            location='{}:{}:{}'.format(self.path, self.line, self.char),
            body=self.body,
            reason=self.reason,
            check=self.check,
            in_patch='yes' if self.revision.contains(self) else 'no',
            third_party='yes' if self.is_third_party() else 'no',
            publishable_check='yes' if self.has_publishable_check() else 'no',
            publishable='yes' if self.is_publishable() else 'no',
            expanded_macro='yes' if self.is_expanded_macro() else 'no',
            is_new='yes' if self.is_new else 'no',
            reliability=self.reliability.value,
            notes='\n'.join([
                ISSUE_NOTE_MARKDOWN.format(
                    message=n.message,
                    location='{}:{}:{}'.format(n.path, n.line, n.char),
                    body=n.body,
                ) for n in self.notes
            ]),
        )

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
            'level': self.level,
            'message': self.message,
            'body': self.body,
            'reason': self.reason,
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
            'reliability': self.reliability.value
        }

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        description = self.message

        # Append to description the reliability index if any
        if self.reliability != Reliability.Unknown:
            description += '\nChecker reliability is {} (false positive risk).'.format(self.reliability.value)

        if self.body:
            description += '\n\n > {}'.format(self.body)
        return LintResult(
            name='Clang-Tidy - {}'.format(self.check),
            description=description,
            code='clang-tidy.{}'.format(self.check),
            severity='warning',
            path=self.path,
            line=self.line,
            char=self.char,
        )


class ClangTidyTask(AnalysisTask):
    '''
    Support issues from source-test clang-tidy tasks
    '''
    artifacts = [
        'public/code-review/clang-tidy.json',
    ]

    def parse_issues(self, artifacts, revision):
        return [
            ClangTidyIssue(
                revision,
                path=self.clean_path(path),
                line=warning['line'],
                char=warning['column'],
                check=warning['flag'],
                message=warning['message'],
                reliability=Reliability(warning['reliability']) if 'reliability' in warning else Reliability.Unknown
            )
            for artifact in artifacts.values()
            for path, items in artifact['files'].items()
            for warning in items['warnings']
        ]
