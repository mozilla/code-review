# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog
from libmozdata.phabricator import LintResult

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot import Reliability
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## coverity error

- **Message**: {message}
- **Location**: {location}
- **Coverity check**: {check}
- **Publishable **: {publishable}
- **Is Clang Error**: {is_clang_error}
- **Is Local**: {is_local}
- **Reliability**: {reliability} (false positive risk)
"""

ERROR_MARKDOWN = """
**Message**: ```{message}```
**Location**: {location}
"""

ISSUE_ELEMENT_IN_STACK = """
- //{file_path}:{line_number}//:
-- `{path_type}: {description}`.
"""

ISSUE_RELATION = """
The path that leads to this defect is:
"""


class CoverityIssue(Issue):
    """
    An issue reported by coverity
    """

    def __init__(self, analyzer, revision, issue, file_path):
        super().__init__(
            analyzer,
            revision,
            file_path,
            line=issue["line"],
            nb_lines=1,
            check=issue["flag"],
            level=Level.Warning,
            message=issue["message"],
        )
        self.reliability = (
            Reliability(issue["reliability"])
            if "reliability" in issue
            else Reliability.Unknown
        )
        self.build_error = issue.get("build_error", False)

        self.state_on_server = issue["extra"]["stateOnServer"]

        # For build errors we don't embed the stack into the message
        if self.build_error:
            return

        # If we have `stack` in the `try` result then embed it in the message.
        if "stack" in issue["extra"]:
            self.message += ISSUE_RELATION
            stack = issue["extra"]["stack"]
            for event in stack:
                # When an event has `path_type` of `caretline` we skip it.
                if event["path_type"] == "caretline":
                    continue
                self.message += ISSUE_ELEMENT_IN_STACK.format(
                    file_path=event["file_path"],
                    line_number=event["line_number"],
                    path_type=event["path_type"],
                    description=event["description"],
                )

    def is_clang_error(self):
        """
        Determine if the current issue is a translation unit error forwarded by Clang
        """
        return "RW.CLANG" in self.check

    def is_local(self):
        """
        The given coverity issue should be only locally stored and not in the
        remote snapshot
        """
        # According to Coverity manual:
        # presentInReferenceSnapshot - True if the issue is present in the reference
        # snapshot specified in the cov-run-desktop command, false if not.
        return (
            self.state_on_server is not None
            and "presentInReferenceSnapshot" in self.state_on_server
            and self.state_on_server["presentInReferenceSnapshot"] is False
        )

    def validates(self):
        """
        Publish only local Coverity issues
        """
        return self.is_local()

    def as_text(self):
        """
        Build the text body published on reporters
        """
        # If there is the reliability index use it
        return (
            f"Checker reliability is {self.reliability.value}, meaning that the false positive ratio is {self.reliability.invert}.\n{self.message}"
            if self.reliability != Reliability.Unknown
            else self.message
        )

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            check=self.check,
            message=self.message,
            location="{}:{}".format(self.path, self.line),
            publishable=self.is_publishable() and "yes" or "no",
            is_local=self.is_local() and "yes" or "no",
            reliability=self.reliability.value,
            is_clang_error=self.is_clang_error() and "yes" or "no",
        )

    def as_error(self):
        assert self.build_error, "CoverityIssue is not a build error."

        return ERROR_MARKDOWN.format(
            message=self.message, location="{}:{}".format(self.path, self.line)
        )

    def as_phabricator_lint(self):
        """
        Outputs a Phabricator lint result
        """
        # If there is the reliability index use it
        message = (
            f"Checker reliability is {self.reliability.value}, meaning that the false positive ratio is {self.reliability.invert}.\n{self.message}"
            if self.reliability != Reliability.Unknown
            else self.message
        )

        return LintResult(
            name=message,
            code="coverity.{}".format(self.check),
            severity="error",
            path=self.path,
            line=self.line,
        )

    def is_build_error(self):
        """
        Return True if Coverity intercepted a build error forwarded by clang.
        """
        return self.build_error


class CoverityTask(AnalysisTask):
    """
    Support remote Coverity analyzer
    """

    artifacts = ["public/code-review/coverity.json"]

    def parse_issues(self, artifacts, revision):
        """
        Parse issues from a pre-translated Coverity report
        """
        assert isinstance(artifacts, dict)
        return [
            CoverityIssue(
                analyzer=self.name, revision=revision, issue=warning, file_path=path
            )
            for artifact in artifacts.values()
            for path, items in artifact["files"].items()
            for warning in items["warnings"]
        ]
