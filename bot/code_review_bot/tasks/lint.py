# -*- coding: utf-8 -*-
import structlog

from code_review_bot import Issue
from code_review_bot import Level
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
        diff=None,
    ):
        base_line = lineno and int(lineno) or 0
        nb_lines = 1

        if diff:
            try:
                base_line, nb_lines = self.parse_diff(diff, base_line)

                # Add diff to message
                message += f"\n```\n{diff}\n```"
            except Exception as e:
                logger.warning(f"Failed to parse diff: {e}")

        # Use analyzer name when check is not provided
        # This happens for analyzers who only have one rule
        if check is None:
            check = analyzer
        super().__init__(
            analyzer,
            revision,
            path,
            line=base_line,
            nb_lines=nb_lines,
            check=check,
            column=column,
            level=Level(level),
            message=message,
        )
        self.linter = linter

    def parse_diff(self, diff, base_line):
        """
        Parse an optional Mozlint diff to get the lines from the original patch
        """
        changes = list(
            filter(
                None,
                [
                    (i, c[0]) if c and c[0] in ("-", "+") else None
                    for i, c in enumerate(diff.splitlines(), start=base_line)
                ],
            )
        )
        assert changes, "No changes in diff"

        # First change has the position of the issue's top line
        base_line, _ = changes[0]

        # We only consider the old lines as being in patch
        nb_lines = len([c for c in changes if c[1] == "-"]) or 1

        return base_line, nb_lines

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
        linter = "{}: {}".format(self.linter, self.check) if self.check else self.linter
        return "{}: {} [{}]".format(self.level.name, message, linter)

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

    # Only process failed states, as a completed task means that no issues were found
    valid_states = ("failed",)
    skipped_states = ("completed",)

    def parse_issues(self, artifacts, revision):
        """
        Parse issues from a log file content
        """
        assert isinstance(artifacts, dict)
        return [
            MozLintIssue(
                analyzer=self.name,
                revision=revision,
                path=issue.get("relpath", issue["path"]),
                column=issue["column"],
                level=issue["level"],
                lineno=issue["lineno"],
                linter=issue["linter"],
                message=issue["message"],
                check=issue["rule"],
                diff=issue.get("diff"),
            )
            for artifact in artifacts.values()
            for _, path_issues in artifact.items()
            for issue in path_issues
        ]
