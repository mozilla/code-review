# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common import log
from cli_common.phabricator import PhabricatorAPI
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.report.base import Reporter
from static_analysis_bot.revisions import PhabricatorRevision

BUG_REPORT_URL = 'https://bit.ly/2IyNRy2'

logger = log.get_logger(__name__)


class PhabricatorReporter(Reporter):
    '''
    API connector to report on Phabricator
    '''
    def __init__(self, configuration={}, *args, **kwargs):
        if kwargs.get('api') is not None:
            self.setup_api(kwargs['api'])

        self.analyzers = configuration.get('analyzers')
        assert self.analyzers is not None, \
            'No analyzers setup on Phabricator reporter'

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info('Phabricator reporter enabled')

    def publish(self, issues, revision):
        '''
        Publish inline comments for each issues
        '''
        if not isinstance(revision, PhabricatorRevision):
            logger.info('Phabricator reporter only publishes Phabricator revisions. Skipping.')
            return None, None

        # Load existing comments for this revision
        existing_comments = self.api.list_comments(revision.phid)
        logger.info('Found {} existing comments on review'.format(len(existing_comments)))

        # Use only publishable issues and patches
        # and avoid publishing a non related patch from an anlyzer partly activated (allowed paths)
        issues = list(filter(lambda i: i.is_publishable() and i.ANALYZER in self.analyzers, issues))
        analyzers_available = set(i.ANALYZER for i in issues).intersection(self.analyzers)
        patches = {
            analyzer: url
            for analyzer, url in revision.improvement_patches.items()
            if analyzer in analyzers_available
        }

        if issues:

            # First publish inlines as drafts
            inlines = list(filter(None, [
                self.comment_inline(revision, issue, existing_comments)
                for issue in issues
            ]))
            if not inlines:
                logger.info('No new comments found, skipping Phabricator publication')
                return
            logger.info('Added inline comments', ids=[i['id'] for i in inlines])

            # Then publish top comment
            self.api.comment(
                revision.id,
                self.build_comment(
                    issues=issues,
                    patches=patches,
                    bug_report_url=BUG_REPORT_URL,
                ),
            )
            stats.api.increment('report.phabricator.issues', len(inlines))
            stats.api.increment('report.phabricator')
            logger.info('Published phabricator comment')

        else:
            # TODO: Publish a validated comment ?
            logger.info('No issues to publish on phabricator')

        return issues, patches

    def comment_inline(self, revision, issue, existing_comments=[]):
        '''
        Post an inline comment on a diff
        '''
        assert isinstance(revision, PhabricatorRevision)
        assert isinstance(issue, Issue)

        # Check if comment is already posted
        comment = {
            'diffID': revision.diff_id,
            'filePath': issue.path,
            'lineNumber': issue.line,
            'lineLength': issue.nb_lines - 1,
            'content': issue.as_text(),
        }
        if comment in existing_comments:
            logger.info('Skipping existing comment', text=comment['content'], filename=comment['filePath'], line=comment['lineNumber'])
            return

        inline = self.api.request(
            'differential.createinline',

            # This displays on the new file (right side)
            # Python boolean is not recognized by Conduit :/
            isNewFile=1,

            # Use comment data
            **comment
        )
        return inline
