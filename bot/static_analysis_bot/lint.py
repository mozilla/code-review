# -*- coding: utf-8 -*-
import itertools
import json
import os

from cli_common.command import run
from cli_common.log import get_logger
from static_analysis_bot import MOZLINT
from static_analysis_bot import AnalysisException
from static_analysis_bot import DefaultAnalyzer
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision
from static_analysis_bot.task import AnalysisTask

logger = get_logger(__name__)

TRY_PREFIX = 'source-test-mozlint'
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

        # Ensure path is always relative to the repository
        self.path = path
        if settings.has_local_clone:
            if self.path.startswith(settings.repo_dir):
                self.path = os.path.relpath(self.path, settings.repo_dir)
            assert os.path.exists(os.path.join(settings.repo_dir, self.path)), \
                'Missing {} in repo {}'.format(self.path, settings.repo_dir)
        elif self.path.startswith('/builds/worker/checkouts/'):
            # Remove Try path prefix
            self.path = self.path[25:]

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


class MozLint(DefaultAnalyzer):
    '''
    Exposes mach lint capabilities
    '''
    def __init__(self):

        # Check we have a Shell set in env
        # This is needed for mach + mozlint execution
        assert 'SHELL' in os.environ, \
            'Missing SHELL environment variable'

    @stats.api.timed('runtime.mozlint')
    def run(self, revision):
        '''
        List all issues found by mozlint on specified files
        '''
        assert isinstance(revision, Revision)

        issues = list(itertools.chain.from_iterable([
            self.find_issues(path, revision) or []
            for path in revision.files
        ]))

        stats.report_issues('mozlint', issues)

        return issues

    def find_issues(self, path, revision):
        '''
        Run mozlint through mach, using gecko-env
        '''
        # Check file exists (before mode)
        full_path = os.path.join(settings.repo_dir, path)
        if not os.path.exists(full_path):
            logger.info('Modified file not found {}'.format(full_path))
            return

        # Run mozlint on a file
        command = [
            'gecko-env',
            './mach', 'lint',
            '-f', 'json',
            '--warnings',
            '--quiet',
            path
        ]
        returncode, output, error = run(' '.join(command), cwd=settings.repo_dir)
        output = output.decode('utf-8')

        # Dump raw mozlint output as a Taskcluster artifact (for debugging)
        output_path = os.path.join(
            settings.taskcluster.results_dir,
            '{}-mozlint.txt'.format(repr(revision)),
        )
        with open(output_path, 'a') as f:
            f.write(output)

        if returncode == 0:
            logger.debug('No Mozlint errors', path=path)
            return
        assert 'error: problem with lint setup' not in output, \
            'Mach lint setup failed'

        # Load output as json
        # Only consider last line, as ./mach lint may output
        # linter setup output on stdout :/
        try:
            lines = list(filter(None, output.split('\n')))
            payload = json.loads(lines[-1])
        except json.decoder.JSONDecodeError:
            raise AnalysisException('mozlint', 'Invalid json output', path=path, lines=lines)

        if full_path not in payload and path not in payload:
            logger.warn('Missing path in linter output', path=path)
            return

        # Mozlint uses both full & relative path to index issues
        return [
            MozLintIssue(revision=revision, **issue)
            for p in (path, full_path)
            for issue in payload.get(p, [])
        ]


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
            MozLintIssue(revision=revision, **issue)
            for artifact in artifacts.values()
            for path, path_issues in artifact.items()
            for issue in path_issues
        ]
