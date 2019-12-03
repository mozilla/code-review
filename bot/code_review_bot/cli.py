# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import os
import sys

import structlog
import yaml
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import AnalysisException
from code_review_bot import stats
from code_review_bot import taskcluster
from code_review_bot.config import settings
from code_review_bot.report import get_reporters
from code_review_bot.revisions import Revision
from code_review_bot.workflow import Workflow
from code_review_tools.log import init_logger

logger = structlog.get_logger(__name__)


def parse_cli():
    """
    Setup CLI options parser
    """
    parser = argparse.ArgumentParser(description="Mozilla Code Review Bot")
    parser.add_argument(
        "-c",
        "--configuration",
        help="Local configuration file replacing Taskcluster secrets",
        type=open,
    )
    parser.add_argument(
        "--taskcluster-secret",
        help="Taskcluster Secret path",
        default=os.environ.get("TASKCLUSTER_SECRET"),
    )
    parser.add_argument("--taskcluster-client-id", help="Taskcluster Client ID")
    parser.add_argument("--taskcluster-access-token", help="Taskcluster Access token")
    return parser.parse_args()


@stats.timer("runtime.analysis")
def main():

    args = parse_cli()
    taskcluster.auth(args.taskcluster_client_id, args.taskcluster_access_token)

    taskcluster.load_secrets(
        args.taskcluster_secret,
        prefixes=["common", "code-review-bot", "bot"],
        required=("APP_CHANNEL", "REPORTERS", "PHABRICATOR", "ALLOWED_PATHS"),
        existing={
            "APP_CHANNEL": "development",
            "REPORTERS": [],
            "PUBLICATION": "IN_PATCH",
            "ZERO_COVERAGE_ENABLED": True,
            "ALLOWED_PATHS": ["*"],
        },
        local_secrets=yaml.safe_load(args.configuration)
        if args.configuration
        else None,
    )

    init_logger(
        "bot",
        channel=taskcluster.secrets.get("APP_CHANNEL", "dev"),
        PAPERTRAIL_HOST=taskcluster.secrets.get("PAPERTRAIL_HOST"),
        PAPERTRAIL_PORT=taskcluster.secrets.get("PAPERTRAIL_PORT"),
        SENTRY_DSN=taskcluster.secrets.get("SENTRY_DSN"),
    )

    # Setup settings before stats
    settings.setup(
        taskcluster.secrets["APP_CHANNEL"],
        taskcluster.secrets["PUBLICATION"],
        taskcluster.secrets["ALLOWED_PATHS"],
    )
    # Setup statistics
    influx_conf = taskcluster.secrets.get("influxdb")
    if influx_conf:
        stats.auth(influx_conf)

    # Load reporters
    reporters = get_reporters(taskcluster.secrets["REPORTERS"])

    # Load index service
    index_service = taskcluster.get_service("index")

    # Load queue service
    queue_service = taskcluster.get_service("queue")

    # Load Phabricator API
    phabricator = taskcluster.secrets["PHABRICATOR"]
    phabricator_reporting_enabled = "phabricator" in reporters
    phabricator_api = PhabricatorAPI(phabricator["api_key"], phabricator["url"])
    if phabricator_reporting_enabled:
        reporters["phabricator"].setup_api(phabricator_api)

    # Load unique revision
    try:
        revision = Revision.from_try(
            queue_service.task(settings.try_task_id), phabricator_api
        )
    except Exception as e:
        # Report revision loading failure on production only
        # On testing or dev instances, we can use different Phabricator
        # configuration that do not match all the pulse messages sent
        if settings.on_production:
            raise

        else:
            logger.info(
                "Failed to load revision",
                task=settings.try_task_id,
                error=str(e),
                phabricator=phabricator["url"],
            )
            return 1

    # Run workflow according to source
    w = Workflow(
        reporters,
        index_service,
        queue_service,
        phabricator_api,
        taskcluster.secrets["ZERO_COVERAGE_ENABLED"],
    )
    try:
        w.run(revision)
    except Exception as e:
        # Log errors to papertrail
        logger.error("Static analysis failure", revision=revision, error=e)

        # Index analysis state
        extras = {}
        if isinstance(e, AnalysisException):
            extras["error_code"] = e.code
            extras["error_message"] = str(e)
        w.index(revision, state="error", **extras)

        # Update Harbormaster status
        revision.update_status(state=BuildState.Fail)

        # Then raise to mark task as erroneous
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
