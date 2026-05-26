# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot import Issue, taskcluster
from code_review_bot.report.base import Reporter
from code_review_bot.revisions import GithubRevision, PhabricatorRevision
from code_review_bot.sources.github import GithubClient

logger = structlog.get_logger(__name__)

EMAIL_SUBJECT = (
    """Code Review bot found {build_errors} build errors on D{phabricator_id}"""
)

EMAIL_HEADER = """
# [Code Review bot](https://github.com/mozilla/code-review) found {build_errors} build errors on [D{phabricator_id}]({review_url})

{content}"""


class BuildErrorsReporter(Reporter):
    """
    In case there are build errors, notify the author of the revision:
    * By email in case of a Phabricator revision
    * In a PR thread in case of a Github revision
    """

    def __init__(self, configuration):
        # Load TC services
        self.notify = taskcluster.get_service("notify")
        self.github_client = GithubClient.from_configuration(configuration)
        logger.info("BuildErrorsReporter report enabled.")

        def publish_github(self, revision: GithubRevision, build_errors: list[Issue]):
            """
            Comment directly on the Pull Request, as a comment mentioning the author
            """
            if not self.github_client:
                logger.error(
                    "Github API client is not initialized, skipping Github reporting"
                )
                return

            messages = [f"Hello @{revision.pull_request.user.login},"]
            messages.append(
                f"[Code Review bot](https://github.com/mozilla/code-review) detected {len(build_errors)} build errors when analyzing this Pull Request:"
            )
            for issue in build_errors:
                messages.append(issue.as_error())

            content = "\n".join(messages)
            self.github_client.publish_comment(revision, content)

        def publish_phabricator(
            self, revision: PhabricatorRevision, build_errors: list[Issue]
        ):
            """
            Notify by email the author of the last commit for this revision
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

            # Since we now know that there is an "author" field we assume that we have "email"
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

    def publish(self, issues, revision, task_failures, links, reviewers):
        build_errors = [issue for issue in issues if issue.is_build_error()]

        if not build_errors:
            logger.info("No build errors encountered.")
            return

        if isinstance(revision, GithubRevision):
            self.publish_github(revision, build_errors)

        elif isinstance(revision, PhabricatorRevision):
            self.publish_phabricator(revision, build_errors)

        else:
            raise NotImplementedError(
                "Only Github and Phabricator revisions are supported"
            )
