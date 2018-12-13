# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common import log
from cli_common.taskcluster import get_service
from static_analysis_bot.config import settings
from static_analysis_bot.report.base import Reporter

logger = log.get_logger(__name__)


EMAIL_STATS_LINE = '* **{source}**: {publishable} publishable ({total} total)'

EMAIL_HEADER = '''
# Found {publishable} publishable issues ({total} total)

{stats}

Review Url: {review_url}

'''
EMAIL_HEADER_PATCH = '* Improvement patch from {}'


class MailReporter(Reporter):
    '''
    Send an email to admins through Taskcluster service
    '''
    def __init__(self, configuration, client_id, access_token):
        self.emails, = self.requires(configuration, 'emails')
        assert len(self.emails) > 0, 'Missing emails data'

        # Load TC services & secrets
        self.notify = get_service(
            'notify',
            client_id=client_id,
            access_token=access_token,
        )

        logger.info('Mail report enabled', emails=self.emails)

    def publish(self, issues, revision):
        '''
        Send an email to administrators
        '''

        # Build stats display for all issues
        # One line per issues class
        stats = '\n'.join([
            EMAIL_STATS_LINE.format(
                source=str(cls.__name__),
                total=stat['total'],
                publishable=stat['publishable'],
            )
            for cls, stat in self.calc_stats(issues).items()
        ])

        content = EMAIL_HEADER.format(
            total=len(issues),
            publishable=sum([i.is_publishable() for i in issues]),
            stats=stats,
            review_url=revision.url,
        )
        if revision.improvement_patches:
            content += '## Improvement patches:\n\n{}\n\n'.format(
                '\n'.join(
                    EMAIL_HEADER_PATCH.format(patch)
                    for patch in revision.improvement_patches
                )
            )
        content += '\n\n'.join([i.as_markdown() for i in issues])
        if len(content) > 102400:
            # Content is 102400 chars max
            content = content[:102000] + '\n\n... Content max limit reached!'
        subject = '[{}] New Static Analysis {}'.format(settings.app_channel, revision)
        for email in self.emails:
            self.notify.email({
                'address': email,
                'subject': subject,
                'content': content,
                'template': 'fullscreen',
            })
