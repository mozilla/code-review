# -*- coding: utf-8 -*-
import functools
import itertools

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


class ClangFormatIssue(Issue):
    """
    An issue created by the Clang Format tool
    """

    def __init__(
        self, analyzer, path, line, nb_lines, revision, column=None, patch=None
    ):
        super().__init__(
            analyzer,
            revision,
            path,
            line,
            nb_lines,
            check="invalid-styling",
            message="The change does not follow the C/C++ coding style, please reformat",
            column=column,
            level=Level.Warning,
        )
        self.patch = patch

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
        if self.patch:
            return "Replace with :\n\n```{}```".format(self.patch)
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
        self.patch += other.patch


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
                        patch=issue["replacement"],
                        revision=revision,
                    )
                    for issue in issues
                ]
            )
            for path, issues in artifact.items()
        }

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
