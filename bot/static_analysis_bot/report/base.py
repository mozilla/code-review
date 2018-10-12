# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools

from static_analysis_bot.clang.format import ClangFormatIssue
from static_analysis_bot.clang.tidy import ClangTidyIssue
from static_analysis_bot.infer.infer import InferIssue
from static_analysis_bot.lint import MozLintIssue

COMMENT_PARTS = {
    ClangTidyIssue: {
        'defect': ' - {nb} found by clang-tidy',
        'analyzer': ' - `./mach static-analysis check path/to/file.cpp` (C/C++)',
    },
    InferIssue: {
        'defect': ' - {nb} found by infer',
        'analyzer': ' - `./mach static-analysis check-java path/to/file.java` (Java)',
    },
    ClangFormatIssue: {
        'defect': ' - {nb} found by clang-format',
        'analyzer': ' - `./mach clang-format -p path/to/file.cpp` (C/C++)',
    },
    MozLintIssue: {
        'defect': ' - {nb} found by mozlint',
        'analyzer': ' - `./mach lint path/to/file` (JS/Python/etc)',
    },
}
COMMENT_FAILURE = '''
Code analysis found {defects_total} in this patch{extras_comments}:
{defects}

You can run this analysis locally with:
{analyzers}
'''
BUG_REPORT = '''
If you see a problem in this automated review, please report it here: {bug_report_url}
'''
COMMENT_DIFF_DOWNLOAD = '''
For your convenience, here is a patch that fixes all the clang-format defects (use it in your repository with `hg import` or `git apply`): {url}
'''


class Reporter(object):
    '''
    Common interface to post reports on a website
    Will configure & build reports
    '''
    def __init__(self, configuration, client_id, access_token):
        '''
        Configure reporter using Taskcluster credentials and configuration
        '''
        raise NotImplementedError

    def publish(self, issues, revision, diff_url):
        '''
        Publish a new report
        '''
        raise NotImplementedError

    def requires(self, configuration, *keys):
        '''
        Check all configuration necessary keys are present
        '''
        assert isinstance(configuration, dict)

        out = []
        for key in keys:
            assert key in configuration, \
                'Missing {} {}'.format(self.__class__.__name__, key)
            out.append(configuration[key])

        return out

    def calc_stats(self, issues):
        '''
        Calc stats about issues:
        * group issues by class name
        * count their total number
        * count their publishable number
        '''
        groups = itertools.groupby(
            sorted(issues, key=lambda x: str(x.__class__)),
            lambda x: x.__class__,
        )

        def stats(items):
            _items = list(items)
            return {
                'total': len(_items),
                'publishable': sum([i.is_publishable() for i in _items])
            }

        from collections import OrderedDict
        return OrderedDict([
            (cls, stats(items))
            for cls, items in groups
        ])

    def build_comment(self, issues, bug_report_url, diff_url=None, max_comments=None):
        '''
        Build a human readable comment about published issues
        '''
        def pluralize(word, nb):
            assert isinstance(word, str)
            assert isinstance(nb, int)
            return '{} {}'.format(nb, nb == 1 and word or word + 's')

        # Calc stats for issues, grouped by class
        stats = self.calc_stats(issues)

        # Build parts depending on issues
        defects, analyzers = [], []
        for cls, cls_stats in stats.items():
            part = COMMENT_PARTS.get(cls)
            assert part is not None, \
                'Unsupported issue class {}'.format(cls)
            defects.append(part['defect'].format(
                nb=pluralize('defect', cls_stats['publishable'])
            ))
            analyzers.append(part['analyzer'])

        # Build top comment
        nb = len(issues)
        extras = ''
        if max_comments is not None and nb > max_comments:
            extras = ' (only the first {} are reported here)'.format(max_comments)

        body = COMMENT_FAILURE
        comment = body.format(
            extras_comments=extras,
            defects_total=pluralize('defect', nb),
            defects='\n'.join(defects),
            analyzers='\n'.join(analyzers),
        )
        if ClangFormatIssue in stats and diff_url is not None:
            comment += COMMENT_DIFF_DOWNLOAD.format(
                url=diff_url,
            )
        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        return comment
