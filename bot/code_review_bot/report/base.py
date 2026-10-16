# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools

from code_review_bot import IssueType, Level
from code_review_bot.tasks.base import BlockedTask

TASKS_BLOCKED = "{count} did not run because of upstream failures: {tasks}"
TASKS_NOT_ANALYSED = (
    "{count} could not be analysed, please check {pronoun} manually: {tasks}"
)

OMITTED_ERROR_DETAILS = (
    "Error details for {count} failed task{plural} were omitted to keep this "
    "message under its size limit; see the linked logs."
)


def format_build_errors(issues, limit, collapsible=False):
    links = [issue.as_error() for issue in issues]
    omitted_note = OMITTED_ERROR_DETAILS.format(count=len(issues), plural="s")
    budget = limit - len("\n".join(links)) - len(omitted_note) - 1

    messages = []
    omitted = 0
    for issue, link in zip(issues, links):
        messages.append(link)
        details = issue.as_error_details(collapsible)
        if not details:
            continue
        if len(details) + 1 <= budget:
            messages.append(details)
            budget -= len(details) + 1
        else:
            omitted += 1

    if omitted:
        messages.append(
            OMITTED_ERROR_DETAILS.format(
                count=omitted, plural="s" if omitted > 1 else ""
            )
        )

    return "\n".join(messages)


class Reporter:
    """
    Common interface to post reports on a website
    Will configure & build reports
    """

    def __init__(self, configuration):
        """
        Configure reporter using Taskcluster credentials and configuration
        """
        raise NotImplementedError

    def publish(self, issues, revision):
        """
        Publish a new report
        """
        raise NotImplementedError

    def requires(self, configuration, *keys):
        """
        Check all configuration necessary keys are present
        """
        assert isinstance(configuration, dict)

        out = []
        for key in keys:
            assert key in configuration, f"Missing {self.__class__.__name__} {key}"
            out.append(configuration[key])

        return out

    def split_task_failures(self, task_failures):
        exceptions = sorted(
            (task for task in task_failures if task.status.get("state") == "exception"),
            key=lambda task: task.name,
        )
        failed = [
            task for task in task_failures if task.status.get("state") != "exception"
        ]
        blocked = [task for task in exceptions if isinstance(task, BlockedTask)]
        not_analysed = [
            task for task in exceptions if not isinstance(task, BlockedTask)
        ]
        return failed, blocked, not_analysed

    def task_failure_summaries(self, task_failures, task_url):
        _, blocked, not_analysed = self.split_task_failures(task_failures)
        return [
            template.format(
                count=f"{len(tasks)} task{'s' if len(tasks) > 1 else ''}",
                pronoun="them" if len(tasks) > 1 else "it",
                tasks=", ".join(f"[{task.name}]({task_url(task)})" for task in tasks),
            )
            for template, tasks in (
                (TASKS_BLOCKED, blocked),
                (TASKS_NOT_ANALYSED, not_analysed),
            )
            if tasks
        ]

    def calc_stats(self, issues):
        """
        Calc stats about issues:
        * group issues by analyzer
        * count their total number
        * count their publishable number
        """

        groups = itertools.groupby(
            sorted(issues, key=lambda i: i.analyzer.name), lambda i: i.analyzer
        )

        def stats(analyzer, items):
            _items = list(items)
            paths = list(
                {
                    i.path
                    for i in _items
                    if i.is_publishable() and i.type_ == IssueType.Lint
                }
            )

            publishable = sum(i.is_publishable() for i in _items)
            build_errors = sum(i.is_build_error() for i in _items)

            return {
                "analyzer": analyzer.display_name,
                "log": analyzer.log,
                "help": analyzer.build_help_message(paths),
                "total": len(_items),
                "publishable": publishable,
                "publishable_paths": paths,
                # Split results for normal publishable issues and build errors
                "nb_defects": publishable - build_errors,
                "nb_build_errors": build_errors,
                "nb_warnings": sum(i.level == Level.Warning for i in _items),
                "nb_errors": sum(i.level == Level.Error for i in _items),
            }

        return [stats(analyzer, items) for analyzer, items in groups]
