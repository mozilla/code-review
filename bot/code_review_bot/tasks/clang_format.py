import rs_parsepatch
import structlog

from code_review_bot import Issue, Level
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

    def __init__(self, analyzer, path, lines, revision):
        assert isinstance(lines, list)
        assert len(lines) > 0, "No lines describing patch"

        # Find position of first different line
        try:
            first_diff = [old != new for old, new, _ in lines].index(True)
        except ValueError:
            first_diff = 0
        lines = lines[first_diff:]

        # Get the lines impacted by the patch
        old_nb, new_nb, _ = zip(*lines)
        line = min(filter(None, old_nb))
        nb_lines = max(filter(None, old_nb)) - line + 1

        # Build the fix to display on reporters
        fix = "\n".join([line.decode("utf-8") for _, nb, line in lines if nb])

        super().__init__(
            analyzer,
            revision,
            path,
            line,
            nb_lines,
            check="invalid-styling",
            fix=fix,
            language="c++",
            message="The change does not follow the C/C++ coding style, please reformat",
            level=Level.Warning,
        )

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
            return f"Replace with :\n\n```{self.patch}```"
        return "Incorrect coding style [clang-format]"

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            path=self.path, line=self.line, nb_lines=self.nb_lines
        )


class ClangFormatTask(AnalysisTask):
    """
    Support issues from source-test clang-format tasks by reading the
    clang-format json output
    """

    artifacts = ["public/code-review/clang-format.diff"]

    @property
    def display_name(self):
        return "clang-format"

    def build_help_message(self, files):
        files = " ".join(files)
        return f"`./mach clang-format -p {files}`"

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get("public/code-review/clang-format.diff")
        if artifact is None:
            logger.warn("Missing clang-format.diff")
            return []

        # Use all chunks provided by parsepatch
        return [
            ClangFormatIssue(
                analyzer=self,
                path=diff["filename"],
                lines=diff["lines"],
                revision=revision,
            )
            for diff in rs_parsepatch.get_diffs(artifact)
        ]

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
