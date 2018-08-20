# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from urllib.parse import urlparse

import requests

from cli_common import log
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.report.base import Reporter
from static_analysis_bot.revisions import PhabricatorRevision

logger = log.get_logger(__name__)

BUG_REPORT_URL = 'https://bit.ly/2tb8Qk3'


class ConduitError(Exception):
    '''
    Exception to be raised when Phabricator returns an error response.
    '''
    def __init__(self, msg, error_code=None, error_info=None):
        super(ConduitError, self).__init__(msg)
        self.error_code = error_code
        self.error_info = error_info
        logger.warn('Conduit API error {} : {}'.format(
            self.error_code,
            self.error_info or 'unknown'
        ))

    @classmethod
    def raise_if_error(cls, response_body):
        '''
        Raise a ConduitError if the provided response_body was an error.
        '''
        if response_body['error_code'] is not None:
            raise cls(
                response_body.get('error_info'),
                error_code=response_body.get('error_code'),
                error_info=response_body.get('error_info')
            )


class PhabricatorReporter(Reporter):
    '''
    API connector to report on Phabricator
    '''
    def __init__(self, configuration, *args):
        self.url, self.api_key = self.requires(configuration, 'url', 'api_key')
        assert self.url.endswith('/api/'), \
            'Phabricator API must end with /api/'

        # Test authentication
        self.user = self.request('user.whoami')
        logger.info('Authenticated on phabricator', url=self.url, user=self.user['realName'])

    @property
    def hostname(self):
        parts = urlparse(self.url)
        return parts.netloc

    def load_diff(self, phid):
        '''
        Find details of a differential diff
        '''
        out = self.request(
            'differential.diff.search',
            constraints={
                'phids': [phid, ],
            },
        )

        data = out['data']
        assert len(data) == 1, \
            'Diff not found'
        return data[0]

    def load_raw_diff(self, diff_id):
        '''
        Load the raw diff content
        '''
        return self.request(
            'differential.getrawdiff',
            diffID=diff_id,
        )

    def load_revision(self, phid):
        '''
        Find details of a differential revision
        '''
        out = self.request(
            'differential.revision.search',
            constraints={
                'phids': [phid, ],
            },
        )

        data = out['data']
        assert len(data) == 1, \
            'Revision not found'
        return data[0]

    def publish(self, issues, revision):
        '''
        Publish inline comments for each issues
        '''
        if not isinstance(revision, PhabricatorRevision):
            logger.info('Phabricator reporter only publishes Phabricator revisions. Skipping.')
            return

        # Load existing comments for this revision
        existing_comments = self.list_comments(revision)
        logger.info('Found {} existing comments on review'.format(len(existing_comments)))

        # Use only publishable issues
        issues = list(filter(lambda i: i.is_publishable(), issues))
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
            self.comment(
                revision,
                self.build_comment(
                    issues=issues,
                    diff_url=revision.diff_url,
                    bug_report_url=BUG_REPORT_URL,
                ),
            )
            stats.api.increment('report.phabricator.issues', len(inlines))
            stats.api.increment('report.phabricator')
            logger.info('Published phabricator comment')

        else:
            # TODO: Publish a validated comment ?
            logger.info('No issues to publish on phabricator')

    def list_comments(self, revision):
        '''
        List and format existing inline comments for a revision
        '''
        transactions = self.request(
            'transaction.search',
            objectIdentifier=revision.phid,
        )
        return [
            {

                'diffID': transaction['fields']['diff']['id'],
                'filePath': transaction['fields']['path'],
                'lineNumber': transaction['fields']['line'],
                'lineLength': transaction['fields']['length'],
                'content': comment['content']['raw'],

            }
            for transaction in transactions['data']
            for comment in transaction['comments']
            if transaction['type'] == 'inline' and transaction['authorPHID'] == self.user['phid']
        ]

    def comment(self, revision, message):
        '''
        Comment on a Differential revision
        Using a frozen method as new transactions does not
        seem to support inlines publication
        '''
        assert isinstance(revision, PhabricatorRevision)

        return self.request(
            'differential.createcomment',
            revision_id=revision.id,
            message=message,
            attach_inlines=1,
        )

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

        inline = self.request(
            'differential.createinline',

            # This displays on the new file (right side)
            # Python boolean is not recognized by Conduit :/
            isNewFile=1,

            # Use comment data
            **comment
        )
        return inline

    def request(self, path, **payload):
        '''
        Send a request to Phabricator API
        '''

        def flatten_params(params):
            '''
            Flatten nested objects and lists.
            Phabricator requires query data in a application/x-www-form-urlencoded
            format, so we need to flatten our params dictionary.
            '''
            assert isinstance(params, dict)
            flat = {}
            remaining = list(params.items())

            # Run a depth-ish first search building the parameter name
            # as we traverse the tree.
            while remaining:
                key, o = remaining.pop()
                if isinstance(o, dict):
                    gen = o.items()
                elif isinstance(o, list):
                    gen = enumerate(o)
                else:
                    flat[key] = o
                    continue

                remaining.extend(('{}[{}]'.format(key, k), v) for k, v in gen)

            return flat

        # Add api token to payload
        payload['api.token'] = self.api_key

        # Run POST request on api
        response = requests.post(
            self.url + path,
            data=flatten_params(payload),
        )

        # Check response
        data = response.json()
        assert response.ok
        assert 'error_code' in data
        ConduitError.raise_if_error(data)

        # Outputs result
        assert 'result' in data
        return data['result']
