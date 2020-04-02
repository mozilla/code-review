# -*- coding: utf-8 -*-
import collections
import functools
import itertools

import requests
import structlog

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## clang-format

- **Path**: {path}
- **Lines**: from {line}, on {nb_lines} lines
"""

# A white space replacement provided by clang-format
# for a specific file, at a precise position (line+column)
Replacement = collections.namedtuple("Replacement", "payload, offset, length")

# Use two type of messages to handle fix presence
# We need the comment between the language declaration and the code block itself
# otherwise Phabricator will automatically remove all lines prefixed by white space
# causing all indentation to be removed.
# Also Phabricator needs 2 spaces to indent the following content
MESSAGE_WITH_FIX = """The change does not follow the C/C++ coding style, it must be formatted as:

  lang=c++
  // Formatting change start at line {line}
{fix}
"""
MESSAGE_WITHOUT_FIX = (
    "The change does not follow the C/C++ coding style, please reformat"
)


class ClangFormatIssue(Issue):
    """
    An issue created by the Clang Format tool
    """

    def __init__(self, analyzer, path, line, nb_lines, revision, replacement, column):
        super().__init__(
            analyzer,
            revision,
            path,
            line,
            nb_lines,
            check="invalid-styling",
            message=MESSAGE_WITHOUT_FIX,
            column=column,
            level=Level.Warning,
        )

        # An issue can be merged with others and accumulate replacements
        assert isinstance(replacement, Replacement)
        self.replacements = [replacement]

    def validates(self):
        """
        Should match one of the allowed paths rules
        """
        return settings.is_allowed_path(self.path)

    def as_text(self):
        """
        Build the text body published on reporters
        According to diff mode
        """
        return "Incorrect coding style [clang-format]"

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            path=self.path, line=self.line, nb_lines=self.nb_lines
        )

    def merge(self, other):
        """
        Merge a neighboring issue with this one, updating nb of lines
        """
        assert isinstance(other, ClangFormatIssue)
        assert other.path == self.path
        assert other.line >= self.line

        self.nb_lines += abs(other.line - (self.line + self.nb_lines - 1))
        self.column = None
        self.replacements += other.replacements

    def render_fix(self, file_content):
        """
        Apply all replacements to the source file
        Update issue's message to showcase the patch
        """
        # Sort replacement from bottom to top
        # to avoid conflicts when updating the same file
        replacements = sorted(
            self.replacements, key=lambda r: r.offset + r.length, reverse=True
        )

        # Apply each replacement
        for r in replacements:
            file_content = (
                file_content[: r.offset]
                + r.payload
                + file_content[r.offset + r.length :]
            )

        # Extract the fixed version, using lines numbers
        # and prefix each line by two spaces to make it a code block on Phabricator
        lines = file_content.splitlines()
        fix = "\n".join(
            map(lambda l: f"  {l}", lines[self.line : self.line + self.nb_lines])
        )

        # Add the fix to the issue's message
        self.message = MESSAGE_WITH_FIX.format(fix=fix, line=self.line)

        return fix


class ClangFormatTask(AnalysisTask):
    """
    Support issues from source-test clang-format tasks by reading the
    clang-format json output
    """

    artifacts = [
        "public/code-review/clang-format.json",
        "public/code-review/clang-format.diff",
    ]

    @property
    def display_name(self):
        return "clang-format"

    def build_help_message(self, files):
        files = " ".join(files)
        return f"`./mach clang-format -s -p {files}` (C/C++)"

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get("public/code-review/clang-format.json")
        if artifact is None:
            logger.warn("Missing clang-format.json")
            return []

        def _group(path_issues):
            # Sort those issues by lines
            path_issues = sorted(path_issues, key=lambda i: i.line)

            def _reducer(acc, issue):
                # Lookup previous issue in accumulated value
                if not acc:
                    return [issue]
                previous = acc[-1]

                if issue.line - (previous.line + previous.nb_lines - 1) > 2:
                    # When two lines are too far apart, keep them distinct
                    acc.append(issue)
                else:
                    # Merge current issue with previous one
                    previous.merge(issue)

                return acc

            # Group all neighboring issues together
            return functools.reduce(_reducer, path_issues, [])

        # Build all issues by paths
        # And group them by neighboring lines
        issues = {
            path: _group(
                [
                    ClangFormatIssue(
                        analyzer=self,
                        path=path,
                        line=issue["line"],
                        nb_lines=issue["lines_modified"],
                        column=issue["line_offset"],
                        replacement=Replacement(
                            issue["replacement"],
                            issue["char_offset"],
                            issue["char_length"],
                        ),
                        revision=revision,
                    )
                    for issue in issues
                ]
            )
            for path, issues in artifact.items()
        }

        # Render the patches for each issue
        for path, path_issues in issues.items():

            # Load the file content
            try:
                file_content = revision.load_file(path)
            except requests.exceptions.HTTPError as e:
                logger.warn(
                    "Failed to load file, clang-format issues won't have patch rendered.",
                    path=path,
                    error=e,
                )
                continue

            # Render the patch using current replacements
            # Issue's message will be updated
            for issue in path_issues:
                issue.render_fix(file_content)

        # Linearize issues
        return list(itertools.chain(*issues.values()))

    def build_patches(self, artifacts):
        artifact = artifacts.get("public/code-review/clang-format.diff")
        if artifact is None:
            logger.warn("Missing or empty clang-format.diff")
            return []

        assert isinstance(artifact, bytes), "clang-format.diff should be bytes"
        patch = artifact.decode("utf-8")
        if patch.strip() == "":
            logger.info("Empty patch in clang-format.diff")
            return []

        return [patch]
