# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

import structlog
from libmozdata.phabricator import LintResult

from code_review_bot import CLANG_TIDY
from code_review_bot import Issue
from code_review_bot import Reliability
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)


ISSUE_MARKDOWN = """
## clang-tidy {level}

- **Message**: {message}
- **Location**: {location}
- **In patch**: {in_patch}
- **Clang check**: {check}
- **Publishable check**: {publishable_check}
- **Expanded Macro**: {expanded_macro}
- **Publishable **: {publishable}
- **Is new**: {is_new}
- **Checker reliability **: {reliability} (false positive risk)

{notes}
"""

ISSUE_NOTE_MARKDOWN = """
- **Note**: {message}
- **Location**: {location}

```
{body}
```
"""

CLANG_MACRO_DETECTION = re.compile(r"^expanded from macro")


class ClangTidyIssue(Issue):
    """
    An issue reported by clang-tidy
    """

    ANALYZER = CLANG_TIDY

    def __init__(
        self,
        analyzer,
        revision,
        path,
        line,
        column,
        check,
        message,
        level="warning",
        reliability=Reliability.Unknown,
        reason=None,
        publish=True,
    ):
        assert isinstance(reliability, Reliability)

        super().__init__(
            analyzer,
            revision,
            path,
            line=int(line),
            nb_lines=1,  # Only 1 line affected on clang-tidy
            check=check,
            column=int(column),
            level=level,
            message=message,
        )
        self.notes = []
        self.reliability = reliability
        self.publishable_check = publish
        self.reason = reason

    def is_problem(self):
        return self.level in ("warning", "error")

    def validates(self):
        """
        Publish clang-tidy issues when:
        * check is marked as publishable
        * is not from an expanded macro
        """
        return self.has_publishable_check() and not self.is_expanded_macro()

    def is_expanded_macro(self):
        """
        Is the issue only found in an expanded macro ?
        """
        if not self.notes:
            return False

        # Only consider first note
        note = self.notes[0]
        return CLANG_MACRO_DETECTION.match(note.message) is not None

    def has_publishable_check(self):
        """
        Is this issue using a publishable check ?
        """
        # Never publish a note (no check attached)
        if not self.is_problem():
            return False

        return self.publishable_check is True

    def as_text(self):
        """
        Build the text body published on reporters
        """
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        body = "{}: {} [clang-tidy: {}]".format(
            self.level.capitalize(), message, self.check
        )

        # Always add body as it's been cleaned up
        if self.reason:
            body += "\n{}".format(self.reason)
        # Also add the reliability of the checker
        if self.reliability != Reliability.Unknown:
            body += "\nChecker reliability is {0}, meaning that the false positive ratio is {1}.".format(
                self.reliability.value, self.reliability.invert
            )
        return body

    def as_markdown(self):
        return ISSUE_MARKDOWN.format(
            level=self.level,
            message=self.message,
            location="{}:{}:{}".format(self.path, self.line, self.column),
            reason=self.reason,
            check=self.check,
            in_patch="yes" if self.revision.contains(self) else "no",
            publishable_check="yes" if self.has_publishable_check() else "no",
            publishable="yes" if self.is_publishable() else "no",
            expanded_macro="yes" if self.is_expanded_macro() else "no",
            is_new="yes" if self.is_new else "no",
            reliability=self.reliability.value,
            notes="\n".join(
                [
                    ISSUE_NOTE_MARKDOWN.format(
                        message=n.message,
                        location="{}:{}:{}".format(n.path, n.line, n.column),
                        body=n.body,
                    )
                    for n in self.notes
                ]
            ),
        )

    def as_phabricator_lint(self):
        """
        Outputs a Phabricator lint result
        """
        description = self.message

        # Append to description the reliability index if any
        if self.reliability != Reliability.Unknown:
            description += "\nChecker reliability is {0}, meaning that the false positive ratio is {1}.".format(
                self.reliability.value, self.reliability.invert
            )

        return LintResult(
            name="Clang-Tidy - {}".format(self.check),
            description=description,
            code="clang-tidy.{}".format(self.check),
            severity="warning",
            path=self.path,
            line=self.line,
            char=self.column,
        )


class ClangTidyTask(AnalysisTask):
    """
    Support issues from source-test clang-tidy tasks
    """

    artifacts = ["public/code-review/clang-tidy.json"]

    def parse_issues(self, artifacts, revision):
        return [
            ClangTidyIssue(
                analyzer=self.name,
                revision=revision,
                path=path,
                line=warning["line"],
                column=warning["column"],
                check=warning["flag"],
                message=warning["message"],
                reliability=Reliability(warning["reliability"])
                if "reliability" in warning
                else Reliability.Unknown,
                reason=warning.get("reason"),
                publish=warning.get("publish"),
            )
            for artifact in artifacts.values()
            for path, items in artifact["files"].items()
            for warning in items["warnings"]
        ]
