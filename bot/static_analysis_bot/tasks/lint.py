# -*- coding: utf-8 -*-
from cli_common.log import get_logger
from cli_common.phabricator import LintResult
from static_analysis_bot import MOZLINT
from static_analysis_bot import Issue
from static_analysis_bot.tasks.base import AnalysisTask

logger = get_logger(__name__)

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

    def __init__(self, path, column, level, lineno, linter, message, rule, revision, **kwargs):
        self.nb_lines = 1
        self.column = column
        self.level = level
        self.line = lineno and int(lineno) or 0  # mozlint sometimes produce strings here
        self.linter = linter
        self.message = message
        self.rule = rule
        self.revision = revision
        self.path = path

    def __str__(self):
        return '{} issue {} {} line {}'.format(
            self.linter,
            self.level,
            self.path,
            self.line,
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
        '''
        return not self.is_third_party() and not self.is_disabled_rule()

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
            )
            for artifact in artifacts.values()
            for path, path_issues in artifact.items()
            for issue in path_issues
        ]
