import argparse
import os
import tempfile

import structlog
import yaml

from code_review_events import community_taskcluster_config, taskcluster_config
from code_review_events.workflow import Events
from code_review_tools.libmozdata import setup as setup_libmozdata
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
        "--cache-root",
        help="Cache root, used to pull changesets",
        default=os.path.join(tempfile.gettempdir(), "pulselistener"),
    )
    parser.add_argument(
        "--taskcluster-secret",
        help="Taskcluster Secret path",
        default=os.environ.get("TASKCLUSTER_SECRET"),
    )
    parser.add_argument("--taskcluster-client-id", help="Taskcluster Client ID")
    parser.add_argument("--taskcluster-access-token", help="Taskcluster Access token")
    return parser.parse_args()


def main():
    args = parse_cli()
    taskcluster_config.auth(args.taskcluster_client_id, args.taskcluster_access_token)
    taskcluster_config.load_secrets(
        args.taskcluster_secret,
        prefixes=["common", "events"],
        required=("admins", "PHABRICATOR", "repositories"),
        existing=dict(
            APP_CHANNEL="development",
            admins=["babadie@mozilla.com", "mcastelluccio@mozilla.com"],
            repositories=[],
            user_blacklist=[],
            autoland_enabled=False,
            mozilla_central_enabled=False,
            skippable_files=[],
        ),
        local_secrets=yaml.safe_load(args.configuration)
        if args.configuration
        else None,
    )

    community_config = taskcluster_config.secrets.get("taskcluster_community")
    if community_config is not None:
        community_taskcluster_config.auth(
            community_config["client_id"], community_config["access_token"]
        )

    init_logger(
        "events",
        channel=taskcluster_config.secrets.get("APP_CHANNEL", "dev"),
        PAPERTRAIL_HOST=taskcluster_config.secrets.get("PAPERTRAIL_HOST"),
        PAPERTRAIL_PORT=taskcluster_config.secrets.get("PAPERTRAIL_PORT"),
        SENTRY_DSN=taskcluster_config.secrets.get("SENTRY_DSN"),
    )

    # Setup libmozdata configuration
    setup_libmozdata("code-review-events")

    events = Events(args.cache_root)
    events.run()


if __name__ == "__main__":
    main()
