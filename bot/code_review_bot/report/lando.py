# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot import Level
from code_review_bot.report.base import Reporter

logger = structlog.get_logger(__name__)

LANDO_MESSAGE = "The code review bot found {errors} {errors_noun} which should be fixed to avoid backout and {warnings} {warnings_noun}."


class LandoReporter(Reporter):
    """
    Update lando with a warning message
    """

    def __init__(self, configuration):
        self.lando_api = None

    def setup_api(self, lando_api):
        logger.info("Publishing warnings to lando is enabled by the bot!")
        self.lando_api = lando_api

    def publish(self, issues, revision, task_failures, links):
        """
        Send an email to administrators
        """
        if self.lando_api is None:
            logger.info("Lando integration is not set!")
            return

        nb_publishable = len([i for i in issues if i.is_publishable()])
        nb_publishable_errors = sum(
            1 for i in issues if i.is_publishable() and i.level == Level.Error
        )

        nb_publishable_warnings = nb_publishable - nb_publishable_errors

        logger.info(
            "Publishing warnings to lando for {0} errors and {1} warnings".format(
                nb_publishable_errors, nb_publishable_warnings
            ),
            revision=revision.id,
            diff=revision.diff["id"],
        )

        try:
            # code-review.events sends an initial warning message to lando to specify that the analysis is in progress,
            # we should remove it
            self.lando_api.del_all_warnings(revision.id, revision.diff["id"])

            if nb_publishable > 0:
                self.lando_api.add_warning(
                    LANDO_MESSAGE.format(
                        errors=nb_publishable_errors,
                        errors_noun="error" if nb_publishable_errors == 1 else "errors",
                        warnings=nb_publishable_warnings,
                        warnings_noun="warning"
                        if nb_publishable_warnings == 1
                        else "warnings",
                    ),
                    revision.id,
                    revision.diff["id"],
                )
        except Exception as ex:
            logger.error(str(ex), exc_info=True)
