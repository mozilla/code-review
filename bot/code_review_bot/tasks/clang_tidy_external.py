# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

import structlog

from code_review_bot import Level
from code_review_bot import Reliability
from code_review_bot.tasks.clang_tidy import ClangTidyIssue
from code_review_bot.tasks.clang_tidy import ClangTidyTask

logger = structlog.get_logger(__name__)


ISSUE_MARKDOWN = """
#### Private Static Analysis {level}

- **Message**: {message}
- **Location**: {location}
- **Clang check**: {check}
- **in an expanded Macro**: {expanded_macro}

{notes}"""

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

BUILD_HELP_MSG = """For private static analysis, please see [our private docs in Mana](https://mana.mozilla.org/wiki/pages/viewpage.action?pageId=130909687), if you cannot access this resource, ask your reviewer to help you resolve the issue."""


class ExternalTidyIssue(ClangTidyIssue):
    """
    An issue reported by source-test-clang-external
    """

    def is_build_error(self):
        return False

    def as_error(self):
        assert self.is_build_error(), "ExternalTidyIssue is not a build error."

        return ERROR_MARKDOWN.format(
            message=self.message, location="{}:{}".format(self.path, self.line)
        )

    def is_expanded_macro(self):
        """
        Is the issue only found in an expanded macro ?
        """
        if not self.notes:
            return False

        # Only consider first note
        note = self.notes[0]
        return CLANG_MACRO_DETECTION.match(note.message) is not None

    def as_text(self):
        """
        Build the text body published on reporters
        """
        message = self.message
        if len(message) > 0:
            message = message[0].capitalize() + message[1:]
        body = "{}: {} [external-tidy: {}]".format(self.level.name, message, self.check)

        # Always add body as it's been cleaned up
        if self.reason:
            body += "\n{}".format(self.reason)
        return body

    def as_markdown_for_phab(self):
        # skip not in patch or not publishable
        if not self.revision.contains(self) or not self.is_publishable():
            return ""

        return ISSUE_MARKDOWN.format(
            level=self.level.value,
            message=self.message,
            location="{}:{}:{}".format(self.path, self.line, self.column),
            check=self.check,
            expanded_macro="yes" if self.is_expanded_macro() else "no",
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


class ExternalTidyTask(ClangTidyTask):
    """
    Support issues from source-test clang-external tasks
    """

    # Note this is currently in fact using the same file name as the
    # normal clang tidy check, but this does NOT pose a problem
    # as artifact names are separated into individual folders per task id.
    artifacts = ["public/code-review/clang-tidy.json"]

    @property
    def display_name(self):
        return "private static analysis"

    def build_help_message(self, files):
        return BUILD_HELP_MSG

    def parse_issues(self, artifacts, revision):
        issues = [
            ExternalTidyIssue(
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
                publish=warning.get("publish")
                and warning["flag"].startswith("mozilla-civet-"),
            )
            for artifact in artifacts.values()
            for path, items in artifact["files"].items()
            for warning in items["warnings"]
        ]
        return issues
