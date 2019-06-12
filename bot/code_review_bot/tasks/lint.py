# -*- coding: utf-8 -*-
import itertools
from datetime import datetime

import structlog
from libmozdata.phabricator import LintResult

from code_review_bot import MOZLINT
from code_review_bot import Issue
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = '''
## mozlint - {linter}

- **Path**: {path}
- **Level**: {level}
- **Line**: {line}
- **Third Party**: {third_party}
- **Disabled rule**: {disabled_rule}
- **Publishable**: {publishable}
- **Is new**: {is_new}

```
{message}
```
'''


class MozLintIssue(Issue):
    ANALYZER = MOZLINT

    def __init__(self, path, column, level, lineno, linter, message, rule, revision, diff=None):
        self.column = column
        self.level = level
        self.line = lineno and int(lineno) or 0  # mozlint sometimes produce strings here
        self.linter = linter
        self.message = message
        self.rule = rule
        self.revision = revision
        self.path = path
        self.diff = diff

        # Calc number of lines from patch when available
        if isinstance(self.diff, str):
            lines = self.diff.splitlines()
            self.nb_lines = len(lines)
        else:
            self.nb_lines = 1

    def __str__(self):
        return '{} issue {} {} line {}'.format(
            self.linter,
            self.level,
            self.path,
            # Display line range when multiple lines are in patch
            '{}-{}'.format(self.line, self.line + self.nb_lines) if self.nb_lines > 1 else self.line,
        )

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'level': self.level,
            'rule': self.rule,
            'linter': self.linter,
            'column': self.column,
        }

    def is_disabled_rule(self):
        '''
        Some rules are disabled:
        * Python "bad" quotes
        '''

        # See https://github.com/mozilla/release-services/issues/777
        if self.linter == 'flake8' and self.rule == 'Q000':
            return True

        return False

    def validates(self):
        '''
        A mozlint issues is publishable when:
        * file is not 3rd party
        * rule is not disabled
        * issues without diff (those are published through a patch)
        '''
        return not self.is_third_party() and not self.is_disabled_rule() and self.diff is None

    def as_text(self):
        '''
        Build the text content for reporters
        '''
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        linter = '{}: {}'.format(self.linter, self.rule) if self.rule else self.linter
        return '{}: {} [{}]'.format(
            self.level.capitalize(),
            message,
            linter,
        )

    def as_markdown(self):
        '''
        Build the Markdown content for debug email
        '''
        return ISSUE_MARKDOWN.format(
            linter=self.linter,
            path=self.path,
            level=self.level,
            line=self.line,
            message=self.message,
            third_party=self.is_third_party() and 'yes' or 'no',
            publishable=self.is_publishable() and 'yes' or 'no',
            disabled_rule=self.is_disabled_rule() and 'yes' or 'no',
            is_new=self.is_new and 'yes' or 'no',
        )

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'mozlint',
            'level': self.level,
            'path': self.path,
            'linter': self.linter,
            'line': self.line,
            'column': self.column,
            'nb_lines': self.nb_lines,
            'rule': self.rule,
            'message': self.message,
            'validation': {
                'third_party': self.is_third_party(),
                'disabled_rule': self.is_disabled_rule(),
            },
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
        }

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        code = self.linter
        name = 'MozLint {}'.format(self.linter.capitalize())
        if self.rule:
            code += '.{}'.format(self.rule)
            name += ' - {}'.format(self.rule)
        return LintResult(
            name=name,
            description=self.message,
            code=code,
            severity=self.level,
            path=self.path,
            line=self.line,
            char=self.column,
        )


class MozLintTask(AnalysisTask):
    '''
    Support issues from source-test mozlint tasks by parsing the raw log
    '''
    artifacts = [
        'public/code-review/mozlint.json',
    ]

    # Only process failed states, as a completed task means than no issues were found
    valid_states = ('failed', )

    def parse_issues(self, artifacts, revision):
        '''
        Parse issues from a log file content
        '''
        assert isinstance(artifacts, dict)
        return [
            MozLintIssue(
                revision=revision,
                path=self.clean_path(path),
                column=issue['column'],
                level=issue['level'],
                lineno=issue['lineno'],
                linter=issue['linter'],
                message=issue['message'],
                rule=issue['rule'],
                diff=issue.get('diff'),
            )
            for artifact in artifacts.values()
            for path, path_issues in artifact.items()
            for issue in path_issues
        ]

    def build_patches(self, artifacts, issues):
        '''
        Build an improvement patch from issues with diff
        Any issue on a file in patch will be posted
        '''
        diff_issues = [
            i
            for i in issues
            if i.revision.has_file(i.path) and i.diff is not None
        ]
        if not diff_issues:
            return []

        header_fmt = '--- {path}\t{date}\n+++ {path}\t{date}\n'

        # Group issues by path
        patch = ''
        for path, path_issues in itertools.groupby(diff_issues, lambda i: i.path):

            if patch:
                patch += '\n'

            # Add header for path
            patch += header_fmt.format(
                date=datetime.utcnow(),
                path=path,
            )

            # Add each diff block, avoiding duplicates
            # sorted by top line
            chunks = []
            for issue in path_issues:
                chunk = (issue.line, issue.as_diff())
                if chunk not in chunks:
                    chunks.append(chunk)
            patch += '\n'.join(c[1] for c in sorted(chunks, key=lambda c: c[0]))

        return [
            ('mozlint', patch),
        ]
