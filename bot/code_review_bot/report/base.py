# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools

from code_review_bot import Level


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
            paths = list({i.path for i in _items if i.is_publishable()})

            publishable = sum(i.is_publishable() for i in _items)
            build_errors = sum(i.is_build_error() for i in _items)

            return {
                "analyzer": analyzer.display_name,
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
