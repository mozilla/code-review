from functools import cached_property

import structlog
from libmozdata.phabricator import UnitResult, UnitResultState

from code_review_bot import BaseIssue, IssueType, Level
from code_review_bot import taskcluster as tc_config
from code_review_bot.tasks.base import LOG_ARTIFACT, TASK_LINK, AnalysisTask
from code_review_bot.tasks.log_errors import extract_error_lines, format_error_lines

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## build failure

- **build**: {task_name}

```
{message}
```
"""

ERROR_MARKDOWN = "* [{display_name}]({task_link}) ([log link]({log_link}))"


class BuildIssue(BaseIssue):
    type_ = IssueType.BuildTest

    def __init__(self, task_id, *args, error_lines=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = task_id
        self.error_lines = error_lines or []

    @cached_property
    def hash(self):
        return f"{self.revision}-{self.display_name}"

    def is_publishable(self):
        # build issues are always publishable; never ignored
        return True

    def validates(self):
        # build issues are always valid; never ignored
        return True

    def as_text(self):
        return self.message

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(task_name=self.display_name, message=self.message)

    def as_error(self):
        task_link = TASK_LINK.format(
            root_url=tc_config.default_url, task_id=self.task_id
        )
        return ERROR_MARKDOWN.format(
            display_name=self.display_name,
            task_link=task_link,
            log_link=self.analyzer.log,
        )

    def as_error_details(self, collapsible=False):
        return format_error_lines(self.error_lines, collapsible)

    def is_build_error(self):
        return True

    def as_phabricator_issue(self):
        return UnitResult(
            namespace="code-review",
            name=self.display_name,
            result=UnitResultState.Fail,
            details=f"Code review bot found a **build error**: \n{self.as_error()}",
            format="remarkup",
        )

    def as_dict(self):
        dict_repr = super().as_dict()
        dict_repr["task_id"] = self.task_id
        dict_repr["error_lines"] = self.error_lines

        return dict_repr


class BuildTask(AnalysisTask):
    artifacts = [LOG_ARTIFACT]
    streamed_artifacts = [LOG_ARTIFACT]
    skipped_states = ("completed",)

    def load_artifact(self, queue_service, artifact_name):
        try:
            return super().load_artifact(queue_service, artifact_name)
        except Exception as e:
            logger.warning(
                "Failed to download build log",
                task_id=self.id,
                run_id=self.run_id,
                artifact=artifact_name,
                error=str(e),
            )
            return None, True

    def extract_log_errors(self, log):
        if log is None:
            return []

        try:
            return extract_error_lines(log)
        except Exception as e:
            logger.warning(
                "Failed to read build log",
                task_id=self.id,
                run_id=self.run_id,
                error=str(e),
            )
            return []

    def parse_issues(self, artifacts, revision):
        issues = []

        if self.state == "failed":
            log = (artifacts or {}).get(LOG_ARTIFACT)
            issues.append(
                BuildIssue(
                    task_id=self.id,
                    analyzer=self,
                    revision=revision,
                    level=Level.Error,
                    message=f"build failed: {self.display_name} ",
                    error_lines=self.extract_log_errors(log),
                )
            )

        return issues
