# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import logging.handlers
import os
import sys

import pkg_resources
import sentry_sdk
import structlog
from sentry_sdk.integrations.logging import LoggingIntegration

root = logging.getLogger()


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
    )
    sentry_sdk.set_tag("site", site)

    if task_id is not None:
        # Add a Taskcluster task id when available
        # It will be shown in a new section called Task on the dashboard
        sentry_sdk.set_context("task", {"task_id": task_id})


class RenameAttrsProcessor(structlog.processors.KeyValueRenderer):
    """
    Rename event_dict keys that will attempt to overwrite LogRecord common
    attributes during structlog.stdlib.render_to_log_kwargs processing
    """

    def __call__(self, logger, method_name, event_dict):
        to_rename = [
            key
            for key in event_dict
            if key in sentry_sdk.integrations.logging.COMMON_RECORD_ATTRS
        ]

        for key in to_rename:
            event_dict[f"{key}_"] = event_dict[key]
            event_dict.pop(key)

        return event_dict


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

    logging.basicConfig(
        format="%(asctime)s.%(msecs)06d [%(levelname)-8s] %(filename)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        level=level,
    )

    # Log to papertrail
    if channel and PAPERTRAIL_HOST and PAPERTRAIL_PORT:
        setup_papertrail(project_name, channel, PAPERTRAIL_HOST, PAPERTRAIL_PORT)

    # Log to sentry
    if channel and SENTRY_DSN:
        setup_sentry(project_name, channel, SENTRY_DSN)

    # Setup structlog
    processors = [
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        RenameAttrsProcessor(),
        # Transpose the 'event_dict' from structlog into keyword arguments for logging.log
        # E.g.: 'event' become 'msg' and, at the end, all remaining values from 'event_dict'
        # are added as 'extra'
        structlog.stdlib.render_to_log_kwargs,
        # Render the message as key=repr(value) for both msg and extra arguments
        structlog.processors.KeyValueRenderer(key_order=["msg"]),
    ]

    structlog.configure(
        processors=processors,
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
