# -*- coding: utf-8 -*-
import structlog
from libmozdata.phabricator import LintResult

from code_review_bot import CLANG_FORMAT
from code_review_bot import Issue
from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## clang-format

- **Path**: {path}
- **Lines**: from {line}, on {nb_lines} lines
- **Is new**: {is_new}
"""


class ClangFormatIssue(Issue):
    """
    An issue created by the Clang Format tool
    """

    ANALYZER = CLANG_FORMAT

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
            column=column,
            level="warning",
        )
        self.is_new = True
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
        return "Warning: Incorrect coding style [clang-format]"

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            path=self.path,
            line=self.line,
            nb_lines=self.nb_lines,
            is_new="yes" if self.is_new else "no",
        )

    def as_phabricator_lint(self):
        """
        Outputs a Phabricator lint result
        """
        description = None
        if self.patch:
            description = "Replace with :\n\n```{}```".format(self.patch)
        return LintResult(
            name="C/C++ style issue",
            description=description,
            code="clang-format",
            severity="warning",
            path=self.path,
            line=self.line,
            char=self.column,
        )


class ClangFormatTask(AnalysisTask):
    """
    Support issues from source-test clang-format tasks by reading the
    clang-format json output
    """

    artifacts = [
        "public/code-review/clang-format.json",
        "public/code-review/clang-format.diff",
    ]

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get("public/code-review/clang-format.json")
        if artifact is None:
            logger.warn("Missing clang-format.json")
            return []

        return [
            ClangFormatIssue(
                analyzer=self.name,
                path=self.clean_path(path),
                line=issue["line"],
                nb_lines=issue["lines_modified"],
                column=issue["line_offset"],
                patch=issue["replacement"],
                revision=revision,
            )
            for path, issues in artifact.items()
            for issue in issues
        ]

    def build_patches(self, artifacts):
        artifact = artifacts.get("public/code-review/clang-format.diff")
        if artifact is None:
            logger.warn("Missing or empty clang-format.diff")
            return []

        assert isinstance(artifact, bytes), "clang-format.diff should be bytes"
        patch = artifact.decode("utf-8")
        if patch == "":
            logger.info("Empty patch in clang-format.diff")
            return []

        return [("clang-format", patch)]
