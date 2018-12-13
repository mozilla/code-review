# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os.path
import time

from cli_common import log
from static_analysis_bot.report.base import Reporter

logger = log.get_logger(__name__)


class DebugReporter(Reporter):
    '''
    Debug the issues found and report through the logs
    Build a json file with all issues details, stored as a TC artifact
    '''
    def __init__(self, output_dir):
        assert os.path.isdir(output_dir), 'Invalid output dir'
        self.report_path = os.path.join(
            output_dir,
            'report.json',
        )

    def publish(self, issues, revision):
        '''
        Display issues choices
        '''
        # Simply output issues details through logging
        logger.info('Debug revision', rev=str(revision))
        for issue in issues:
            logger.info(
                'Issue {}'.format('publishable' if issue.is_publishable() else 'silent'),
                issue=str(issue),
            )
        for patch in revision.improvement_patches:
            logger.info('Patch {}'.format(patch))

        # Output json report in public directory
        report = {
            'time': time.time(),
            'revision': revision.as_dict(),
            'issues': [
                issue.as_dict()
                for issue in issues
            ],
            'patches': {
                patch.analyzer: patch.url or patch.path
                for patch in revision.improvement_patches
            },
        }
        with open(self.report_path, 'w') as f:
            json.dump(report, f)
