# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot import taskcluster
from code_review_bot.report.base import Reporter

logger = structlog.get_logger(__name__)

EMAIL_SUBJECT = (
    """Code Review bot found {build_errors} build errors on D{phabricator_id}"""
)

EMAIL_HEADER = """
# [Code Review bot](https://github.com/mozilla/code-review) found {build_errors} build errors on [D{phabricator_id}]({review_url})

{content}"""


class BuildErrorsReporter(Reporter):
    """
    Send an email to the author of the revision in case there are build errors
    """

    def __init__(self, configuration):
        # Load TC services
        self.notify = taskcluster.get_service("notify")

        logger.info("BuildErrorsReporter report enabled.")

    def publish(self, issues, revision, task_failures, links, reviewers):
        """
        Send an email to the author of the revision
        """
        assert (
            revision.phabricator_id and revision.phabricator_phid
        ), "PhabricatorRevision must have a Phabricator ID and PHID"
        assert (
            "attachments" in revision.diff
        ), f"Unable to find the commits for revision with phid {revision.phabricator_phid}."

        attachments = revision.diff["attachments"]

        if "commits" not in attachments and "commits" not in attachments["commits"]:
            logger.info(
                f"Unable to find the commits for revision with phid {revision.phabricator_phid}."
            )
            return

        build_errors = [issue for issue in issues if issue.is_build_error()]

        if not build_errors:
            logger.info("No build errors encountered.")
            return

        content = EMAIL_HEADER.format(
            build_errors=len(build_errors),
            phabricator_id=revision.phabricator_id,
            review_url=revision.url,
            content="\n".join([i.as_error() for i in build_errors]),
        )

        if len(content) > 102400:
            # Content is 102400 chars max
            content = content[:102000] + "\n\n... Content max limit reached!"

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
                "subject": EMAIL_SUBJECT.format(
                    build_errors=len(build_errors),
                    phabricator_id=revision.phabricator_id,
                ),
                "content": content,
            }
        )
