# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import logging.handlers
import os
import re

import pkg_resources
import sentry_sdk
import structlog
from sentry_sdk.integrations.logging import LoggingIntegration

root = logging.getLogger()

# Found on https://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
# 7-bit C1 ANSI sequences
ANSI_ESCAPE = re.compile(
    r"""
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
""",
    re.VERBOSE,
)


class AppNameFilter(logging.Filter):
    def __init__(self, project_name, channel, *args, **kwargs):
        self.project_name = project_name
        self.channel = channel
        super().__init__(*args, **kwargs)

    def filter(self, record):
        record.app_name = f"code-review/{self.channel}/{self.project_name}"
        return True


def setup_papertrail(project_name, channel, PAPERTRAIL_HOST, PAPERTRAIL_PORT):
    """
    Setup papertrail account using taskcluster secrets
    """

    # Setup papertrail
    papertrail = logging.handlers.SysLogHandler(
        address=(PAPERTRAIL_HOST, int(PAPERTRAIL_PORT)),
    )
    formatter = logging.Formatter(
        "%(app_name)s: %(asctime)s %(filename)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    papertrail.setLevel(logging.INFO)
    papertrail.setFormatter(formatter)
    # This filter is used to add the 'app_name' value to all logs to be formatted
    papertrail.addFilter(AppNameFilter(project_name, channel))
    root.addHandler(papertrail)


def remove_color_codes(event, hint):
    """
    Remove ANSI color codes from a Sentry event before it gets published
    """

    def _remove(content):
        try:
            return ANSI_ESCAPE.sub("", content)
        except Exception as e:
            # Do not log here, rely on simple print
            print(f"Failed to remove color code: {e}")
            return content

    # Remove from breadcrumb
    breadcrumbs = event.get("breadcrumbs", {})
    for value in breadcrumbs.get("values", []):
        if "message" in value:
            value["message"] = _remove(value["message"])

    # Remove from log entry
    logentry = event.get("logentry", {})
    if "message" in logentry:
        logentry["message"] = _remove(logentry["message"])

    return event


def setup_sentry(name, channel, dsn):
    """
    Setup sentry account using taskcluster secrets
    """
    # Detect environment
    task_id = os.environ.get("TASK_ID")
    if task_id is not None:
        site = "taskcluster"
    elif "DYNO" in os.environ:
        site = "heroku"
    else:
        site = "unknown"

    # This integration allows sentry to catch logs from logging and process them
    # By default, the 'event_level' is set to ERROR, we are defining it to WARNING
    sentry_logging = LoggingIntegration(
        level=logging.INFO,  # Capture INFO and above as breadcrumbs
        event_level=logging.WARNING,  # Send WARNINGs as events
    )
    # sentry_sdk will automatically retrieve the 'extra' attribute from logs and
    # add contained values as Additional Data on the dashboard of the Sentry issue
    sentry_sdk.init(
        dsn=dsn,
        integrations=[sentry_logging],
        server_name=name,
        environment=channel,
        release=pkg_resources.get_distribution(f"code-review-{name}").version,
        before_send=remove_color_codes,
    )
    sentry_sdk.set_tag("site", site)

    if task_id is not None:
        # Add a Taskcluster task id when available
        # It will be shown in a new section called Task on the dashboard
        sentry_sdk.set_context("task", {"task_id": task_id})


def init_logger(
    project_name,
    channel=None,
    level=logging.INFO,
    PAPERTRAIL_HOST=None,
    PAPERTRAIL_PORT=None,
    SENTRY_DSN=None,
):
    if not channel:
        channel = os.environ.get("APP_CHANNEL")

    # Render extra information from structlog on default logging output
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)06d [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Log to papertrail
    if channel and PAPERTRAIL_HOST and PAPERTRAIL_PORT:
        setup_papertrail(project_name, channel, PAPERTRAIL_HOST, PAPERTRAIL_PORT)

    # Log to sentry
    if channel and SENTRY_DSN:
        setup_sentry(project_name, channel, SENTRY_DSN)

    # Setup structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.dev.ConsoleRenderer(),
    ]

    structlog.configure(
        processors=processors,
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
