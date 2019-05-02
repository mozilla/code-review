# -*- coding: utf-8 -*-
import os
import subprocess

import hglib
from parsepatch.patch import Patch

from cli_common.log import get_logger
from cli_common.phabricator import LintResult
from static_analysis_bot import CLANG_FORMAT
from static_analysis_bot import DefaultAnalyzer
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision
from static_analysis_bot.task import AnalysisTask

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## clang-format

- **Path**: {path}
- **Lines**: from {line}, on {nb_lines} lines
- **Is new**: {is_new}
'''


class ClangFormat(DefaultAnalyzer):
    '''
    Clang Format direct Runner
    List potential issues on modified files
    from a patch
    '''
    def __init__(self):
        self.diff = ''

    @stats.api.timed('runtime.clang-format')
    def run(self, revision):
        '''
        Run ./mach clang-format on all of the C/C++ files from the patch
        '''
        assert isinstance(revision, Revision)

        cmd = [
            'gecko-env',
            './mach', '--log-no-times', 'clang-format', '-p'
        ]

        # Returns a list of eligible files for format
        def get_eligible_files():
            files = []
            # Append to the files list each C/C++ file for format
            for file in revision.files:
                # Verify if file is clang-format compliant, meaning that's a C/C++
                _, ext = os.path.splitext(file)
                if ext.lower() in frozenset.union(settings.cpp_extensions, settings.cpp_header_extensions):
                    files.append(file)
            return files

        files_to_format = get_eligible_files()

        if not files_to_format:
            logger.info('No eligible files found to format.')
            return []

        # Append to the cmd the files that will be formatted
        cmd += files_to_format

        # Run command and commit the current revision for `./mach clang-format ...` to reformat its changes
        logger.info('Running ./mach clang-format', cmd=' '.join(cmd))
        clang_output = subprocess.check_output(
            cmd, cwd=settings.repo_dir).decode('utf-8')

        # Dump raw clang-format output as a Taskcluster artifact (for debugging)
        clang_output_path = os.path.join(
            settings.taskcluster.results_dir,
            '{}-clang-format.txt'.format(repr(revision)),
        )
        with open(clang_output_path, 'w') as f:
            f.write(clang_output)

        # Look for any fixes `./mach clang-format` may have found
        # on allowed files
        allowed_paths = [
            os.path.join(settings.repo_dir, path).encode('utf-8')  # needed for hglib
            for path in filter(settings.is_allowed_path, revision.files)
        ]
        client = hglib.open(settings.repo_dir)
        self.diff = client.diff(files=allowed_paths, unified=8).decode('utf-8')

        if not self.diff:
            return []

        # Store that diff as an improvement patch sent to devs
        revision.add_improvement_patch('clang-format', self.diff)

        # Generate a reverse diff for `parsepatch` (in order to get original
        # line numbers from the dev's patch instead of new line numbers)
        reverse_diff = client.diff(unified=8, reverse=True).decode('utf-8')

        # List all the lines that were fixed by `./mach clang-format`
        patch = Patch.parse_patch(reverse_diff, skip_comments=False)
        assert patch != {}, \
            'Empty patch'

        # Build `ClangFormatIssue`s
        issues = []
        for filename, diff in patch.items():
            lines = sorted(diff.get('touched', []) + diff.get('added', []) + diff.get('deleted', []))
            assert len(lines) > 0, 'No modified lines on {}'.format(filename)

            # Group consecutive lines together (algorithm by calixte)
            groups = []
            group = [lines[0]]
            for line in lines[1:]:
                # If the line is not consecutive with the group, start a new
                # group
                if line != group[-1] + 1:
                    groups.append(group)
                    group = []
                group.append(line)

            # Don't forget to add the last group
            groups.append(group)

            issues += [
                ClangFormatIssue(filename, g[0], len(g), revision)
                for g in groups
            ]

        stats.report_issues('clang-format', issues)
        return issues


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
            logger.warn('Missing clang-format.diff')
            return []

        assert isinstance(artifact, bytes), 'clang-format.diff should be bytes'
        patch = artifact.decode('utf-8')
        if patch == '':
            logger.info('Empty patch in clang-format.diff')
            return []

        return [
            ('clang-format', patch)
        ]
