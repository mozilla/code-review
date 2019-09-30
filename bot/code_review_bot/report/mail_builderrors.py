# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot import taskcluster
from code_review_bot.report.base import Reporter

logger = structlog.get_logger(__name__)

EMAIL_HEADER = """
# Found {build_errors} build errors.

Review Url: {review_url}

"""


class BuildErrorsReporter(Reporter):
    """
    Send an email to the author of the revision in case there are build errors
    """

    def __init__(self, configuration):
        # Load TC services
        self.notify = taskcluster.get_service("notify")

        logger.info("BuildErrorsReporter report enabled.")

    def publish(self, issues, revision):
        """
        Send an email to the author of the revision
        """

        assert (
            "attachments" in revision.diff
        ), "Unable to find the commits for revision {}.".format(revision.phid)

        attachments = revision.diff["attachments"]

        if "commits" not in attachments and "commits" not in attachments["commits"]:
            logger.info(
                "Unable to find the commits for revision {}.".format(revision.phid)
            )
            return

        build_errors = [issue for issue in issues if issue.is_build_error()]

        if not build_errors:
            logger.info("No build errors encountered.")
            return

        content = EMAIL_HEADER.format(
            build_errors=len(build_errors), review_url=revision.url
        )

        content += "\n\n".join([i.as_markdown() for i in build_errors])

        if len(content) > 102400:
            # Content is 102400 chars max
            content = content[:102000] + "\n\n... Content max limit reached!"

        subject = "Build errors encountered for {}".format(revision)

        # Get the last commit
        commit = attachments["commits"]["commits"][-1]

        if "author" not in commit:
            logger.info("Unable to find the author for commit.")
            return

        logger.info("Send build error email", to=commit["author"]["email"])

        # Since we nw know that there is an "author" field we assume that we have "email"
        self.notify.email(
            {
                "address": commit["author"]["email"],
                "subject": subject,
                "content": content,
            }
        )
