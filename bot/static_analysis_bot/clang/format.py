# -*- coding: utf-8 -*-
import difflib
import os
import subprocess

from cli_common.log import get_logger
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

OPCODE_REPLACE = 'replace'
OPCODE_INSERT = 'insert'
OPCODE_DELETE = 'delete'
OPCODES = (OPCODE_REPLACE, OPCODE_INSERT, OPCODE_DELETE,)

ISSUE_MARKDOWN = '''
## clang-format

- **Path**: {path}
- **Mode**: {mode}
- **Lines**: from {line}, on {nb_lines} lines
- **Is new**: {is_new}

Old lines:

```
{old}
```

New lines:

```
{new}
```
'''


class ClangFormat(object):
    '''
    Clang Format direct Runner
    List potential issues on modified files
    from a patch
    '''
    def __init__(self):
        self.binary = os.path.join(
            os.environ['MOZBUILD_STATE_PATH'],
            'clang-tools', 'clang', 'bin', 'clang-format',
        )
        assert os.path.exists(self.binary), \
            'Missing clang-format in {}'.format(self.binary)

    @stats.api.timed('runtime.clang-format')
    def run(self, revision):
        '''
        Run clang-format on those modified files
        '''
        assert isinstance(revision, Revision)
        issues = []
        for path in revision.files:

            # Check file extension is supported
            _, ext = os.path.splitext(path)
            if ext not in settings.cpp_extensions:
                logger.info('Skip clang-format for non C/C++ file', path=path)
                continue

            # Build issues for modified file
            issues += self.run_clang_format(path, revision)

        return issues

    def run_clang_format(self, filename, revision):
        '''
        Clang-format is very fast, no need for a worker queue here
        '''
        # Check file exists (before mode)
        full_path = os.path.join(settings.repo_dir, filename)
        if not os.path.exists(full_path):
            logger.info('Modified file not found {}'.format(full_path))
            return []

        # Build command line for a filename
        cmd = [
            self.binary,

            # Use style from directories
            '-style=file',

            full_path,
        ]
        logger.info('Running clang-format', cmd=' '.join(cmd))

        # Run command
        clang_output = subprocess.check_output(cmd, cwd=settings.repo_dir).decode('utf-8')

        # Dump raw clang-format output as a Taskcluster artifact (for debugging)
        clang_output_path = os.path.join(
            settings.taskcluster_results_dir,
            '{}-clang-format.txt'.format(repr(revision)),
        )
        with open(clang_output_path, 'w') as f:
            f.write(clang_output)

        # Compare output with original file
        src_lines = [x.rstrip('\n') for x in open(full_path).readlines()]
        clang_lines = clang_output.split('\n')

        # Build issues from diff of diff !
        diff = difflib.SequenceMatcher(
            a=src_lines,
            b=clang_lines,
        )
        issues = [
            ClangFormatIssue(filename, src_lines, clang_lines, opcode, revision)
            for opcode in diff.get_opcodes()
            if opcode[0] in OPCODES
        ]

        stats.report_issues('clang-format', issues)
        return issues


class ClangFormatIssue(Issue):
    '''
    An issue created by Clang Format tool
    '''
    def __init__(self, path, a, b, opcode, revision):
        self.mode, self.positions = opcode[0], opcode[1:]
        assert self.mode in OPCODES
        assert isinstance(self.positions, tuple)
        assert len(self.positions) == 4
        self.path = path
        self.revision = revision

        # Lines used to make the diff
        # replace: a[i1:i2] should be replaced by b[j1:j2].
        # delete: a[i1:i2] should be deleted.
        # insert: b[j1:j2] should be inserted at a[i1:i1].
        # These indexes are starting from 1
        # need to offset them
        i1, i2, j1, j2 = self.positions
        self.old = '\n'.join(a[i1 - 1:i2])
        self.new = self.mode != OPCODE_DELETE and '\n'.join(b[j1 - 1:j2])

        # i1 is alsways the starting point
        i1, i2, j1, j2 = self.positions
        self.line = i1
        if self.mode == OPCODE_INSERT:
            self.line -= 1
            self.nb_lines = 1
        else:
            assert i2 > i1
            self.nb_lines = i2 - i1 + 1

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {
            'mode': self.mode,
        }

    def __str__(self):
        return 'clang-format issue {} {} line {}-{}'.format(
            self.path,
            self.mode,
            self.line,
            self.nb_lines,
        )

    def validates(self):
        '''
        No specific rule on clang-format issues
        '''
        return True

    def as_text(self):
        '''
        Build the text body published on reporters
        According to diff mode
        '''
        out = 'Warning: Incorrect coding style [clang-format]\n'
        if self.mode == OPCODE_REPLACE:
            out += 'Replace by: \n\n{}\n'.format(self.new)

        elif self.mode == OPCODE_INSERT:
            out += 'Insert at this line: \n\n{}\n'.format(self.new)

        elif self.mode == OPCODE_DELETE:
            if self.nb_lines > 1:
                out += 'Delete these {} lines'.format(self.nb_lines)
            out += 'Delete this line.'

        else:
            raise Exception('Unsupported mode')

        return out

    def as_markdown(self):
        '''
        Build the Markdown content for debug email
        '''
        return ISSUE_MARKDOWN.format(
            path=self.path,
            mode=self.mode,
            line=self.line,
            nb_lines=self.nb_lines,
            is_new='yes' if self.is_new else 'no',
            old=self.old,
            new=self.new,
        )

    def as_diff(self):
        '''
        Build the standard diff output
        '''
        def _prefix_lines(content, char):
            return '\n'.join([
                '{} {}'.format(char, line)
                for line in content.split('\n')
            ])

        i1, i2, j1, j2 = self.positions
        if self.mode == OPCODE_REPLACE:
            patch = [
                '{},{}c{},{}'.format(i1, i2, j1, j2),
                _prefix_lines(self.old, '<'),
                '---',
                _prefix_lines(self.new, '>')
            ]

        elif self.mode == OPCODE_INSERT:
            patch = [
                '{}a{},{}'.format(i1, j1, j2),
                _prefix_lines(self.new, '>'),
            ]

        elif self.mode == OPCODE_DELETE:
            patch = [
                '{},{}d{},{}'.format(i1, i2, j1, j2),
                _prefix_lines(self.old, '<'),
            ]

        else:
            raise Exception('Invalid mode')

        return '\n'.join(patch) + '\n'

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'clang-format',
            'mode': self.mode,
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'old_lines': self.old,
            'new_lines': self.new,
            'diff': self.as_diff(),
            'validation': {
            },
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
        }
