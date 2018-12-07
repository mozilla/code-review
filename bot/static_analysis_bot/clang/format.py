# -*- coding: utf-8 -*-
import os
import subprocess

import hglib
from parsepatch.patch import Patch

from cli_common.log import get_logger
from static_analysis_bot import CLANG_FORMAT
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## clang-format

- **Path**: {path}
- **Lines**: from {line}, on {nb_lines} lines
- **Is new**: {is_new}
'''


class ClangFormat(object):
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
        Run ./mach clang-format on the current patch
        '''
        assert isinstance(revision, Revision)

        # Commit the current revision for `./mach clang-format` to reformat its changes
        cmd = [
            'gecko-env',
            './mach', '--log-no-times', 'clang-format',
        ]
        logger.info('Running ./mach clang-format', cmd=' '.join(cmd))

        # Run command
        clang_output = subprocess.check_output(cmd, cwd=settings.repo_dir).decode('utf-8')

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
            lines = sorted(diff.get('touched', []) + diff.get('added', []))

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
                ClangFormatIssue(filename, group[0], len(group), revision)
                for group in groups
            ]

        stats.report_issues('clang-format', issues)
        return issues


class ClangFormatIssue(Issue):
    '''
    An issue created by the Clang Format tool
    '''
    ANALYZER = CLANG_FORMAT

    def __init__(self, path, line, nb_lines, revision):
        self.path = path
        self.line = line
        self.nb_lines = nb_lines
        self.revision = revision
        self.is_new = True

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
        }
