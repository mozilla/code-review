# -*- coding: utf-8 -*-
import structlog
from libmozdata.phabricator import LintResult

from static_analysis_bot import CLANG_FORMAT
from static_analysis_bot import Issue
from static_analysis_bot.config import settings
from static_analysis_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = '''
## clang-format

- **Path**: {path}
- **Lines**: from {line}, on {nb_lines} lines
- **Is new**: {is_new}
'''


class ClangFormatIssue(Issue):
    '''
    An issue created by the Clang Format tool
    '''
    ANALYZER = CLANG_FORMAT

    def __init__(self, path, line, nb_lines, revision, column=None, patch=None):
        self.path = path
        self.line = line
        self.nb_lines = nb_lines
        self.revision = revision
        self.is_new = True
        self.patch = patch
        self.column = column

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'nb_lines': self.nb_lines,
        }

    def __str__(self):
        return 'clang-format issue {} line {}-{}'.format(
            self.path,
            self.line,
            self.nb_lines,
        )

    def validates(self):
        '''
        Should match one of the allowed paths rules
        '''
        return settings.is_allowed_path(self.path) \
            and not self.is_third_party()

    def as_text(self):
        '''
        Build the text body published on reporters
        According to diff mode
        '''
        return 'Warning: Incorrect coding style [clang-format]'

    def as_markdown(self):
        '''
        Build the Markdown content for debug email
        '''
        return ISSUE_MARKDOWN.format(
            path=self.path,
            line=self.line,
            nb_lines=self.nb_lines,
            is_new='yes' if self.is_new else 'no',
        )

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'clang-format',
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'validation': {
            },
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
            'patch': self.patch,
            'column': self.column,
        }

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        description = None
        if self.patch:
            description = 'Replace with :\n\n```{}```'.format(self.patch)
        return LintResult(
            name='C/C++ style issue',
            description=description,
            code='clang-format',
            severity='warning',
            path=self.path,
            line=self.line,
            char=self.column,
        )


class ClangFormatTask(AnalysisTask):
    '''
    Support issues from source-test clang-format tasks by reading the
    clang-format json output
    '''
    artifacts = [
        'public/code-review/clang-format.json',
        'public/code-review/clang-format.diff',
    ]

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get('public/code-review/clang-format.json')
        if artifact is None:
            logger.warn('Missing clang-format.json')
            return []

        return [
            ClangFormatIssue(
                path=self.clean_path(path),
                line=issue['line'],
                nb_lines=issue['lines_modified'],
                column=issue['line_offset'],
                patch=issue['replacement'],
                revision=revision,
            )
            for path, issues in artifact.items()
            for issue in issues
        ]

    def build_patches(self, artifacts):
        artifact = artifacts.get('public/code-review/clang-format.diff')
        if artifact is None:
            logger.warn('Missing or empty clang-format.diff')
            return []

        assert isinstance(artifact, bytes), 'clang-format.diff should be bytes'
        patch = artifact.decode('utf-8')
        if patch == '':
            logger.info('Empty patch in clang-format.diff')
            return []

        return [
            ('clang-format', patch)
        ]
