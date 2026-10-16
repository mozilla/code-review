from functools import cached_property

from libmozdata.phabricator import UnitResult, UnitResultState

from code_review_bot import BaseIssue, IssueType, Level
from code_review_bot import taskcluster as tc_config
from code_review_bot.tasks.base import TASK_LINK, AnalysisTask

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

    def __init__(self, task_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = task_id

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

        return dict_repr


class BuildTask(AnalysisTask):
    def parse_issues(self, artifacts, revision):
        issues = []

        if self.state == "failed":
            issues.append(
                BuildIssue(
                    task_id=self.id,
                    analyzer=self,
                    revision=revision,
                    level=Level.Error,
                    message=f"build failed: {self.display_name} ",
                )
            )

        return issues
