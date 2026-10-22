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
from taskcluster.download import downloadArtifactToBuf

from code_review_bot import (
    AnalysisException,
    InvalidRepository,
    InvalidTrigger,
    stats,
    taskcluster,
)
from code_review_bot.analysis import AnalysisMode, get_test_mode_string
from code_review_bot.config import settings
from code_review_bot.report import get_reporters
from code_review_bot.revisions import PhabricatorRevision, Revision
from code_review_bot.revisions.phabricator import find_build_test_target
from code_review_bot.tools.libmozdata import setup as setup_libmozdata
from code_review_bot.tools.log import init_logger
from code_review_bot.workflow import Workflow

logger = structlog.get_logger(__name__)


LANDO_FAILURE_MESSAGE = "{test_mode_string} did not run due to a generic failure."


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
    parser.add_argument(
        "--github-repository",
        help="Optional path to a up-to-date github repository matching the analyzed revision.\n"
        "This argument is required for Github revisions in order to compute issues' hashes based on file content.",
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
        prefixes=["common", "events", "code-review-bot", "bot"],
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
            "ssh_key": None,
            "user_blacklist": [],
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

    os.environ["PHABRICATOR_EDGE_KEY"] = taskcluster.secrets.get(
        "PHABRICATOR_EDGE_KEY", ""
    )

    # Setup settings before stats
    settings.setup(
        taskcluster.secrets["APP_CHANNEL"],
        taskcluster.secrets["ALLOWED_PATHS"],
        taskcluster.secrets["repositories"],
        taskcluster.secrets["ssh_key"],
        args.mercurial_repository,
        args.github_repository,
        backend_parallel_requests=taskcluster.secrets.get("BACKEND_PARALLEL_REQUESTS"),
        taskcluster_parallel_requests=taskcluster.secrets.get(
            "TASKCLUSTER_PARALLEL_REQUESTS"
        ),
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

    # We need Phabricator API to list black-listed users
    settings.load_user_blacklist(taskcluster.secrets["user_blacklist"], phabricator_api)

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

    revision = None
    # Load unique revision
    try:
        if settings.generic_group_id:
            # Only Phabricator revisions is supported from decision task
            revision = PhabricatorRevision.from_decision_task(
                queue_service.task(settings.generic_group_id), phabricator_api
            )
            w.ingest_revision(revision, settings.generic_group_id)
        elif settings.phabricator_build_target:
            # TODO: remove this block once the phabricator build plan
            # no longer fires the analysis task for build/test
            if settings.analysis_mode == AnalysisMode.BuildTest:
                logger.info(
                    "Build/test analysis is started by the Lint analysis, nothing to do"
                )
                return 0

            # Only Phabricator revisions is supported from build target
            revision = PhabricatorRevision.from_phabricator_trigger(
                settings.phabricator_build_target,
                phabricator_api,
            )
            if revision is None:
                return 0

            if not revision.build_test_feature and phabricator_reporting_enabled:
                build_test_target_phid = find_build_test_target(
                    phabricator_api, revision.build_target_phid
                )
                # build/test feature is not enabled for this revision; just
                # pass the build
                phabricator_api.update_build_target(
                    build_test_target_phid, BuildState.Pass
                )

            w.start_analysis(revision)
        else:
            decision_task = queue_service.task(settings.try_group_id)
            rawParams, _ = downloadArtifactToBuf(
                taskId=settings.try_group_id,
                name="public/parameters.yml",
                queueService=queue_service,
            )
            parameters = yaml.safe_load(bytes(rawParams))

            build_target_phid = parameters["phabricator_diff"]

            # for phabricator-driven analysis, we only get the linting
            # build target in the parameters. if we're running publication
            # for the build/test tasks, we need to find and set this to the
            # correct target to make sure the right Build on phabricator is
            # updated
            if build_target_phid and settings.analysis_mode == AnalysisMode.BuildTest:
                build_target_phid = find_build_test_target(
                    phabricator_api, build_target_phid
                )

            revision = Revision.from_try_decision_task(
                decision_task,
                build_target_phid,
                phabricator_api,
            )

            w.run(revision, settings.analysis_mode)

    except InvalidTrigger as e:
        logger.info("Early stop analysis due to invalid trigger", error=str(e))

        # Stop cleanly as we just want to ignore that case
        return 0
    except InvalidRepository as e:
        logger.warning("Early stop analysis due to invalid repository", error=str(e))

        # Stop cleanly as we just want to ignore that case, but report on sentry through warning
        return 0
    except Exception as e:
        if not revision:
            # Report revision loading failure on production only
            # On testing or dev instances, we can use different Phabricator
            # configuration that do not match all the pulse messages sent
            if settings.on_production:
                raise

            else:
                logger.info(
                    "Failed to load revision",
                    task=settings.try_group_id,
                    error=str(e),
                    phabricator=phabricator["url"],
                )
                return 1

        # Log errors to papertrail
        logger.error(
            "Static analysis failure", revision=revision, error=e, exc_info=True
        )

        # Index analysis state
        extras = {}
        if isinstance(e, AnalysisException):
            extras["error_code"] = e.code
            extras["error_message"] = str(e)

        if settings.phabricator_build_target:
            # analysis task: we have one task, and must always deal with
            # both analysis modes
            analysis_modes = [AnalysisMode.Lint, AnalysisMode.BuildTest]
            namespace_suffixes = ["", "lint", "build-test"]
        elif settings.analysis_mode == AnalysisMode.BuildTest:
            # publication task for build-test checks
            analysis_modes = [AnalysisMode.BuildTest]
            namespace_suffixes = ["build-test"]
        elif settings.analysis_mode == AnalysisMode.Lint:
            # publication task for lint checks
            analysis_modes = [AnalysisMode.Lint]
            namespace_suffixes = ["", "lint"]
        else:
            # ingestion mode; linting and build/test are irrelevant
            analysis_modes = []
            namespace_suffixes = [""]

        w.index(
            revision, namespace_suffixes=namespace_suffixes, state="error", **extras
        )

        # Update Phabricator
        failure = UnitResult(
            namespace="code-review",
            name="general",
            result=UnitResultState.Broken,
            details="WARNING: A generic error occurred in the code review bot.",
            format="remarkup",
            duration=0,
        )

        # only run when phabricator reporting is enabled, and we're running in
        # a mode that sets a build target (analysis or publication)
        if (
            phabricator_reporting_enabled
            and isinstance(revision, PhabricatorRevision)
            and revision.build_target_phid
        ):
            # in the analysis task, this will always be set to the lint build target,
            # because that's the only one that fires an analysis task
            # in the publication task, this will be either the lint or build/test
            # build target
            w.phabricator.update_build_target(
                revision.build_target_phid, BuildState.Fail, unit=[failure]
            )
            if settings.phabricator_build_target:
                # in the analysis task, we need to additionally append the
                # build/test build target, to make sure we fail it, too
                try:
                    build_test_build_target = find_build_test_target(
                        phabricator_api, revision.build_target_phid
                    )
                    w.phabricator.update_build_target(
                        build_test_build_target, BuildState.Fail, unit=[failure]
                    )
                except Exception:
                    logger.exception("Failed to set build/test build target to Fail")

        # Also update lando
        if not hasattr(revision, "id") or not hasattr(revision, "diff"):
            logger.info(
                "Skipping lando generic failure publication as the revision is incomplete"
            )
        elif lando_publish_generic_failure:
            for analysis_mode in analysis_modes:
                try:
                    test_mode_string = get_test_mode_string(analysis_mode)
                    warnings = lando_api.get_warnings(revision.id, revision.diff["id"])
                    to_delete = [
                        w
                        for w in warnings
                        if w["data"]["message"].startswith(test_mode_string)
                    ]
                    if to_delete:
                        lando_api.del_warnings(to_delete)

                    lando_api.add_warning(
                        LANDO_FAILURE_MESSAGE.format(test_mode_string=test_mode_string),
                        revision.id,
                        revision.diff["id"],
                    )
                except Exception as ex:
                    logger.error(str(ex), exc_info=True)

        # Then raise to mark task as erroneous
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
