# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import os
import sys
from pathlib import Path

import structlog
import yaml
from libmozdata.lando import LandoWarnings
from libmozdata.phabricator import (
    BuildState,
    PhabricatorAPI,
    UnitResult,
    UnitResultState,
)

from code_review_bot import AnalysisException, stats, taskcluster
from code_review_bot.config import settings
from code_review_bot.report import get_reporters
from code_review_bot.revisions import Revision
from code_review_bot.workflow import Workflow
from code_review_tools.libmozdata import setup as setup_libmozdata
from code_review_tools.log import init_logger

logger = structlog.get_logger(__name__)


LANDO_FAILURE_MESSAGE = (
    "Static analysis and linting did not run due to a generic failure."
)


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
    parser.add_argument(
        "--mercurial-repository",
        help="Optional path to a up-to-date mercurial repository matching the analyzed revision.\n"
        "Reduce the time required to read updated files, i.e. to compute the unique hash of multiple issues.\n"
        "A clone is automatically performed when ingesting a revision and this option is unset, "
        "except on a developer instance (where HGMO is used).",
        type=Path,
        default=None,
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
        required=(
            "APP_CHANNEL",
            "REPORTERS",
            "PHABRICATOR",
            "ALLOWED_PATHS",
            "repositories",
        ),
        existing={
            "APP_CHANNEL": "development",
            "REPORTERS": [],
            "ZERO_COVERAGE_ENABLED": True,
            "ALLOWED_PATHS": ["*"],
            "task_failures_ignored": [],
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

    # Setup libmozdata configuration
    setup_libmozdata("code-review-bot")

    # Setup settings before stats
    settings.setup(
        taskcluster.secrets["APP_CHANNEL"],
        taskcluster.secrets["ALLOWED_PATHS"],
        taskcluster.secrets["repositories"],
        args.mercurial_repository,
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
    phabricator_reporting_enabled = "phabricator" in reporters and phabricator.get(
        "publish", False
    )
    phabricator_api = PhabricatorAPI(phabricator["api_key"], phabricator["url"])
    if phabricator_reporting_enabled:
        reporters["phabricator"].setup_api(phabricator_api)

    # lando the Lando API
    lando_reporting_enabled = "lando" in reporters
    lando_api = None
    lando_publish_generic_failure = False
    if lando_reporting_enabled:
        if taskcluster.secrets["LANDO"].get("publish", False):
            lando_api = LandoWarnings(
                api_url=taskcluster.secrets["LANDO"]["url"],
                api_key=phabricator["api_key"],
            )
            lando_publish_generic_failure = taskcluster.secrets["LANDO"][
                "publish_failure"
            ]
            reporters["lando"].setup_api(lando_api)

    # Load unique revision
    try:
        if settings.autoland_group_id:
            revision = Revision.from_decision_task(
                queue_service.task(settings.autoland_group_id), phabricator_api
            )
        elif settings.mozilla_central_group_id:
            revision = Revision.from_decision_task(
                queue_service.task(settings.mozilla_central_group_id), phabricator_api
            )
        elif settings.phabricator_revision_phid:
            revision = Revision.from_phabricator_trigger(
                settings.phabricator_revision_phid,
                settings.phabricator_transactions,
                phabricator_api,
            )
        else:
            revision = Revision.from_try_task(
                queue_service.task(settings.try_task_id),
                queue_service.task(settings.try_group_id),
                phabricator_api,
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
        # Update build status only when phabricator reporting is enabled
        update_build=phabricator_reporting_enabled,
        task_failures_ignored=taskcluster.secrets["task_failures_ignored"],
    )
    try:
        if settings.autoland_group_id:
            w.ingest_revision(revision, settings.autoland_group_id)
        elif settings.mozilla_central_group_id:
            w.ingest_revision(revision, settings.mozilla_central_group_id)
        elif settings.phabricator_revision_phid:
            w.start_analysis(revision)
        else:
            w.run(revision)
    except Exception as e:
        # Log errors to papertrail
        logger.error(
            "Static analysis failure", revision=revision, error=e, exc_info=True
        )

        # Index analysis state
        extras = {}
        if isinstance(e, AnalysisException):
            extras["error_code"] = e.code
            extras["error_message"] = str(e)
        w.index(revision, state="error", **extras)

        # Update Phabricator
        failure = UnitResult(
            namespace="code-review",
            name="general",
            result=UnitResultState.Broken,
            details="WARNING: A generic error occurred in the code review bot.",
            format="remarkup",
            duration=0,
        )

        if phabricator_reporting_enabled:
            w.phabricator.update_build_target(
                revision.build_target_phid, BuildState.Fail, unit=[failure]
            )

        # Also update lando
        if not hasattr(revision, "id") or not hasattr(revision, "diff"):
            logger.info(
                "Skipping lando generic failure publication as the revision is incomplete"
            )
        elif lando_publish_generic_failure:
            try:
                lando_api.del_all_warnings(revision.id, revision.diff["id"])
                lando_api.add_warning(
                    LANDO_FAILURE_MESSAGE, revision.id, revision.diff["id"]
                )
            except Exception as ex:
                logger.error(str(ex), exc_info=True)

        # Then raise to mark task as erroneous
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
