# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

import structlog

from code_review_bot import Issue
from code_review_bot import Level
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

ERROR_MARKDOWN = """
**Message**: ```{message}```
**Location**: {location}
"""

CLANG_MACRO_DETECTION = re.compile(r"^expanded from macro")


class ClangTidyIssue(Issue):
    """
    An issue reported by clang-tidy
    """

    def __init__(
        self,
        analyzer,
        revision,
        path,
        line,
        column,
        check,
        message,
        level=Level.Warning,
        reliability=Reliability.Unknown,
        reason=None,
        publish=True,
        force_publish=False,
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
        self.force_publish = force_publish

    def is_build_error(self):
        return True if self.level == Level.Error else False

    def as_error(self):
        assert self.is_build_error(), "ClangTidyIssue is not a build error."

        return ERROR_MARKDOWN.format(
            message=self.message, location="{}:{}".format(self.path, self.line)
        )

    @property
    def display_name(self):
        """
        Display name to identify clearly if it's static-analysis issue or a
        build error
        """
        return "Build Error" if self.is_build_error() else self.analyzer.display_name

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
        return self.publishable_check is True

    def as_text(self):
        """
        Build the text body published on reporters
        """
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        body = "{}: {} [clang-tidy: {}]".format(self.level.name, message, self.check)

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
            level=self.level.value,
            message=self.message,
            location="{}:{}:{}".format(self.path, self.line, self.column),
            reason=self.reason,
            check=self.check,
            in_patch="yes" if self.revision.contains(self) else "no",
            publishable_check="yes" if self.has_publishable_check() else "no",
            publishable="yes" if self.is_publishable() else "no",
            expanded_macro="yes" if self.is_expanded_macro() else "no",
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


class ClangTidyTask(AnalysisTask):
    """
    Support issues from source-test clang-tidy tasks
    """

    artifacts = ["public/code-review/clang-tidy.json"]

    @property
    def display_name(self):
        return "clang-tidy"

    def build_help_message(self, files):
        return "`./mach static-analysis check --outgoing` (C/C++)"

    def parse_issues(self, artifacts, revision):
        return [
            ClangTidyIssue(
                analyzer=self,
                revision=revision,
                path=path,
                line=warning["line"],
                column=warning["column"],
                check=warning["flag"],
                level=Level(warning.get("type", "warning")),
                message=warning["message"],
                reliability=Reliability(warning["reliability"])
                if "reliability" in warning
                else Reliability.Unknown,
                reason=warning.get("reason"),
                publish=warning.get("publish"),
                force_publish=warning.get("publish_mandatory"),
            )
            for artifact in artifacts.values()
            for path, items in artifact["files"].items()
            for warning in items["warnings"]
        ]
