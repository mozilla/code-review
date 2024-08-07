import structlog

from code_review_bot import Issue, Level, taskcluster
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## issue {analyzer}

- **Path**: {path}
- **Level**: {level}
- **Check**: {check}
- **Line**: {line}
- **Publishable**: {publishable}

```
{message}
```
"""


class DefaultIssue(Issue):
    def validates(self):
        """
        Default issues are valid as long as they match the format
        """
        return True

    def as_text(self):
        """
        Build the text content for reporters
        """
        return f"{self.level.name}: {self.message} [{self.check}]"

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            analyzer=self.analyzer.name,
            path=self.path,
            check=self.check,
            level=self.level.value,
            line=self.line,
            message=self.message,
            publishable=self.is_publishable() and "yes" or "no",
        )


class DefaultTask(AnalysisTask):
    """
    Support issues using the code review format
    https://github.com/mozilla/code-review/blob/master/docs/analysis_format.md
    """

    artifacts = ["public/code-review/issues.json"]

    def parse_issues(self, artifacts, revision):
        """
        Parse issues from a log file content
        """
        assert isinstance(artifacts, dict)

        def default_check(issue):
            # Use analyzer name when check is not provided
            # This happens for analyzers who only have one rule
            # This logic could become the standard once most analyzers
            # use that format
            check = issue.get("check")
            if check:
                return check
            return issue.get("analyzer", self.name)

        return [
            DefaultIssue(
                analyzer=self,
                revision=revision,
                path=issue["path"],
                line=issue["line"],
                column=issue["column"],
                nb_lines=issue.get("nb_lines", 1),
                level=Level(issue["level"]),
                check=default_check(issue),
                message=issue["message"],
            )
            for artifact in artifacts.values()
            for _, path_issues in artifact.items()
            for issue in path_issues
        ]

    @staticmethod
    def matches(task_id):
        """
        Check if the default task can work on a task
        * Lookup the available latest artifacts
        * Check if any artifact matches the official default path
        """
        queue = taskcluster.get_service("queue")
        result = queue.listLatestArtifacts(task_id)
        if "artifacts" not in result:
            return False

        names = set(artifact["name"] for artifact in result["artifacts"])
        return len(names.intersection(DefaultTask.artifacts)) > 0
