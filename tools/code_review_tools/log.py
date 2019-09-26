# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

import logbook
import logbook.more
import raven
import raven.handlers.logbook
import structlog


class UnstructuredRenderer(structlog.processors.KeyValueRenderer):
    def __call__(self, logger, method_name, event_dict):
        event = None
        if "event" in event_dict:
            event = event_dict.pop("event")
        if event_dict or event is None:
            # if there are other keys, use the parent class to render them
            # and append to the event
            rendered = super(UnstructuredRenderer, self).__call__(
                logger, method_name, event_dict
            )
            return f"{event} ({rendered})"
        else:
            return event


def setup_papertrail(project_name, channel, PAPERTRAIL_HOST, PAPERTRAIL_PORT):
    """
    Setup papertrail account using taskcluster secrets
    """

    # Setup papertrail
    papertrail = logbook.SyslogHandler(
        application_name=f"code-review/{channel}/{project_name}",
        address=(PAPERTRAIL_HOST, int(PAPERTRAIL_PORT)),
        level=logbook.INFO,
        format_string="{record.time} {record.channel}: {record.message}",
        bubble=True,
    )
    papertrail.push_application()


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

    sentry_client = raven.Client(
        dsn=dsn,
        site=site,
        name=name,
        environment=channel,
        release=raven.fetch_package_version(f"code-review-{name}"),
    )

    if task_id is not None:
        # Add a Taskcluster task id when available
        # It will be shown in the Additional Data section on the dashboard
        sentry_client.context.merge({"extra": {"task_id": task_id}})

    sentry_handler = raven.handlers.logbook.SentryHandler(
        sentry_client, level=logbook.WARNING, bubble=True
    )
    sentry_handler.push_application()


def init_logger(
    project_name,
    channel=None,
    level=logbook.INFO,
    PAPERTRAIL_HOST=None,
    PAPERTRAIL_PORT=None,
    SENTRY_DSN=None,
):

    if not channel:
        channel = os.environ.get("APP_CHANNEL")

    # Output logs on stderr, with color support on consoles
    fmt = "{record.time} [{record.level_name:<8}] {record.channel}: {record.message}"
    handler = logbook.more.ColorizedStderrHandler(level=level, format_string=fmt)
    handler.push_application()

    # Log to papertrail
    if channel and PAPERTRAIL_HOST and PAPERTRAIL_PORT:
        setup_papertrail(project_name, channel, PAPERTRAIL_HOST, PAPERTRAIL_PORT)

    # Log to senty
    if channel and SENTRY_DSN:
        setup_sentry(project_name, channel, SENTRY_DSN)

    def logbook_factory(*args, **kwargs):
        # Logger given to structlog
        logbook.compat.redirect_logging()
        return logbook.Logger(level=level, *args, **kwargs)

    # Setup structlog over logbook, with args list at the end
    processors = [
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        UnstructuredRenderer(),
    ]

    structlog.configure(
        context_class=structlog.threadlocal.wrap_dict(dict),
        processors=processors,
        logger_factory=logbook_factory,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
