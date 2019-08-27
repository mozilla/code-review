# -*- coding: utf-8 -*-
import argparse
import asyncio
import os
import tempfile

import structlog
from libmozevent import taskcluster_config
from libmozevent.bus import MessageBus
from libmozevent.log import init_logger
from libmozevent.mercurial import MercurialWorker
from libmozevent.monitoring import Monitoring
from libmozevent.pulse import run_consumer
from libmozevent.web import WebServer

from code_review_events import QUEUE_MERCURIAL
from code_review_events import QUEUE_MONITORING
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import QUEUE_WEB_BUILDS
from code_review_events.workflow import CodeReview

logger = structlog.get_logger(__name__)


def parse_cli():
    """
    Setup CLI options parser
    """
    parser = argparse.ArgumentParser(description="Mozilla Code Review Bot")
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


class Events(object):
    """
    Listen to HTTP notifications from phabricator and trigger new try jobs
    """

    def __init__(self, cache_root):
        # Create message bus shared amongst process
        self.bus = MessageBus()

        self.workflow = CodeReview(
            api_key=taskcluster_config.secrets["PHABRICATOR"]["api_key"],
            url=taskcluster_config.secrets["PHABRICATOR"]["url"],
            publish=taskcluster_config.secrets["PHABRICATOR"].get("publish", False),
            risk_analysis_reviewers=taskcluster_config.secrets.get(
                "risk_analysis_reviewers", []
            ),
        )
        self.workflow.register(self.bus)

        # Build mercurial worker & queue
        self.mercurial = MercurialWorker(
            QUEUE_MERCURIAL,
            QUEUE_PHABRICATOR_RESULTS,
            repositories=self.workflow.get_repositories(
                taskcluster_config.secrets["repositories"], cache_root
            ),
        )
        self.mercurial.register(self.bus)

        # Create web server
        self.webserver = WebServer(QUEUE_WEB_BUILDS)
        self.webserver.register(self.bus)

        # Setup monitoring for newly created tasks
        self.monitoring = Monitoring(
            QUEUE_MONITORING, taskcluster_config.secrets["admins"], 7 * 3600
        )
        self.monitoring.register(self.bus)

    def run(self):
        consumers = [
            # Code review main workflow
            self.workflow.run(),
            # Add mercurial task
            self.mercurial.run(),
            # Add monitoring task
            self.monitoring.run(),
        ]

        # Publish results on Phabricator
        if self.workflow.publish:
            consumers.append(
                self.bus.run(self.workflow.publish_results, QUEUE_PHABRICATOR_RESULTS)
            )

        # Start the web server in its own process
        web_process = self.webserver.start()

        # Run all tasks concurrently
        run_consumer(asyncio.gather(*consumers))

        if self.workflow:
            web_process.join()


def main():
    args = parse_cli()
    taskcluster_config.auth(args.taskcluster_client_id, args.taskcluster_access_token)
    taskcluster_config.load_secrets(
        args.taskcluster_secret,
        "events",
        required=("admins", "PHABRICATOR", "repositories"),
        existing=dict(
            admins=["babadie@mozilla.com", "mcastelluccio@mozilla.com"], repositories=[]
        ),
    )

    init_logger(
        "code_review_events",
        PAPERTRAIL_HOST=taskcluster_config.secrets.get("PAPERTRAIL_HOST"),
        PAPERTRAIL_PORT=taskcluster_config.secrets.get("PAPERTRAIL_PORT"),
        SENTRY_DSN=taskcluster_config.secrets.get("SENTRY_DSN"),
    )

    events = Events(args.cache_root)
    events.run()


if __name__ == "__main__":
    main()
