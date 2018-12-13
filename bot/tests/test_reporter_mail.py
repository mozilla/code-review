# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import responses

MAIL_CONTENT = '''
# Found 3 publishable issues (5 total)

* **MockIssue**: 3 publishable (5 total)

Review Url: https://phabricator.test/D51

## Improvement patches:

* Improvement patch from clang-tidy: {results}/clang-tidy-PHID-DIFF-test.diff
* Improvement patch from clang-format: {results}/clang-format-PHID-DIFF-test.diff

This is the mock issue n°0

This is the mock issue n°1

This is the mock issue n°2

This is the mock issue n°3

This is the mock issue n°4'''


@responses.activate
def test_conf(mock_config):
    '''
    Test mail reporter configuration
    '''
    from static_analysis_bot.report.mail import MailReporter

    # Missing emails conf
    with pytest.raises(AssertionError):
        MailReporter({}, 'test_tc', 'token_tc')

    # Missing emails
    conf = {
        'emails': [],
    }
    with pytest.raises(AssertionError):
        MailReporter(conf, 'test_tc', 'token_tc')

    # Valid emails
    conf = {
        'emails': [
            'test@mozilla.com',
        ],
    }
    r = MailReporter(conf, 'test_tc', 'token_tc')
    assert r.emails == ['test@mozilla.com', ]

    conf = {
        'emails': [
            'test@mozilla.com',
            'test2@mozilla.com',
            'test3@mozilla.com',
        ],
    }
    r = MailReporter(conf, 'test_tc', 'token_tc')
    assert r.emails == ['test@mozilla.com', 'test2@mozilla.com', 'test3@mozilla.com']


@responses.activate
def test_mail(mock_config, mock_issues, mock_phabricator):
    '''
    Test mail sending through Taskcluster
    '''
    from static_analysis_bot.report.mail import MailReporter
    from static_analysis_bot.revisions import PhabricatorRevision, ImprovementPatch

    def _check_email(request):
        payload = json.loads(request.body)

        assert payload['subject'] in (
            '[test] New Static Analysis Phabricator #42 - PHID-DIFF-test',
        )
        assert payload['address'] == 'test@mozilla.com'
        assert payload['template'] == 'fullscreen'
        assert payload['content'] == MAIL_CONTENT.format(results=mock_config.taskcluster.results_dir)

        return (200, {}, '')  # ack

    # Add mock taskcluster email to check output
    responses.add_callback(
        responses.POST,
        'https://notify.taskcluster.net/v1/email',
        callback=_check_email,
    )

    # Publish email
    conf = {
        'emails': [
            'test@mozilla.com',
        ],
    }
    r = MailReporter(conf, 'test_tc', 'token_tc')

    with mock_phabricator as api:
        prev = PhabricatorRevision('PHID-DIFF-test', api)
        prev.improvement_patches = [
            ImprovementPatch('clang-tidy', repr(prev), 'Some code fixes'),
            ImprovementPatch('clang-format', repr(prev), 'Some lint fixes'),
        ]
        list(map(lambda p: p.write(), prev.improvement_patches))  # trigger local write
        r.publish(mock_issues, prev)

    # Check stats
    mock_cls = mock_issues[0].__class__
    assert r.calc_stats(mock_issues) == {
        mock_cls: {
            'total': 5,
            'publishable': 3,
        }
    }
