import structlog

from code_review_bot import Issue, Level
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## mozlint - {linter}

- **Path**: {path}
- **Level**: {level}
- **Line**: {line}
- **Disabled check**: {disabled_check}
- **Publishable**: {publishable}

```
{message}
```
"""


def parse_line_range(lineno, lineoffset=None):
    """
    Compute the first line and number of lines covered by a mozlint issue.

    mozlint documents `lineoffset` as a `(<lineno offset>, <num lines>)` tuple,
    but most linters (ruff, clippy, compare-locales, ...) provide a flat integer,
    i.e. the number of extra lines spanned after `lineno`. Support both.
    """
    # mozlint sometimes produce strings here
    line = lineno and int(lineno) or 0
    if not line or lineoffset is None:
        return line, 1

    try:
        if isinstance(lineoffset, list | tuple):
            offset, count = (int(v) for v in lineoffset)
            start = line + offset
            end = start + max(count, 1) - 1
        else:
            start = line
            end = line + int(lineoffset)
    except (TypeError, ValueError):
        logger.warning("Invalid mozlint lineoffset", lineoffset=lineoffset)
        return line, 1

    # Always include the reported line in the range
    start, end = max(min(start, line), 1), max(end, line)
    return start, end - start + 1


class MozLintIssue(Issue):
    def __init__(
        self,
        analyzer,
        path,
        column,
        level,
        lineno,
        linter,
        message,
        check,
        revision,
        lineoffset=None,
        **kwargs,
    ):
        # Use analyzer name when check is not provided
        # This happens for analyzers who only have one rule
        if check is None:
            check = analyzer.name
        line, nb_lines = parse_line_range(lineno, lineoffset)
        super().__init__(
            analyzer,
            revision,
            path,
            line=line,
            nb_lines=nb_lines,
            check=check,
            column=column,
            level=Level(level),
            message=message,
        )
        self.linter = linter

    def is_disabled_check(self):
        """
        Some checks are disabled:
        * Python "bad" quotes
        """

        # See https://github.com/mozilla/release-services/issues/777
        if self.linter == "flake8" and self.check == "Q000":
            return True

        return False

    def validates(self):
        """
        A mozlint issues is publishable when:
        * check is not disabled
        """
        return not self.is_disabled_check()

    def as_text(self):
        """
        Build the text content for reporters
        """
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        linter = f"{self.linter}: {self.check}" if self.check else self.linter
        return f"{self.level.name}: {message} [{linter}]"

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            linter=self.linter,
            path=self.path,
            level=self.level.value,
            line=self.line,
            message=self.message,
            publishable=self.is_publishable() and "yes" or "no",
            disabled_check=self.is_disabled_check() and "yes" or "no",
        )


class MozLintTask(AnalysisTask):
    """
    Support issues from source-test mozlint tasks by parsing the raw log
    """

    artifacts = ["public/code-review/mozlint.json"]

    @property
    def linter(self):
        # Detect linter from task name
        if not self.name.startswith("source-test-mozlint-"):
            return
        return self.name[20:]

    @property
    def display_name(self):
        if self.linter:
            return f"{self.linter} (Mozlint)"
        if self.name.startswith("source-test-"):
            return self.name[12:]
        return self.name

    def build_help_message(self, files):
        return "`./mach lint --warnings --outgoing`"

    def parse_issues(self, artifacts, revision):
        """
        Parse issues from a log file content
        """
        assert isinstance(artifacts, dict)
        return [
            MozLintIssue(
                analyzer=self,
                revision=revision,
                path=issue.get("relpath", issue["path"]),
                column=issue["column"],
                level=issue["level"],
                lineno=issue["lineno"],
                lineoffset=issue.get("lineoffset"),
                linter=issue["linter"],
                message=issue["message"],
                check=issue["rule"],
            )
            for artifact in artifacts.values()
            for _, path_issues in artifact.items()
            for issue in path_issues
        ]
