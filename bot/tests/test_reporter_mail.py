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
def test_conf(mock_config, mock_taskcluster_config):
    '''
    Test mail reporter configuration
    '''
    from static_analysis_bot.report.mail import MailReporter

    # Missing emails conf
    with pytest.raises(AssertionError):
        MailReporter({})

    # Missing emails
    conf = {
        'emails': [],
    }
    with pytest.raises(AssertionError):
        MailReporter(conf)

    # Valid emails
    conf = {
        'emails': [
            'test@mozilla.com',
        ],
    }
    r = MailReporter(conf)
    assert r.emails == ['test@mozilla.com', ]

    conf = {
        'emails': [
            'test@mozilla.com',
            'test2@mozilla.com',
            'test3@mozilla.com',
        ],
    }
    r = MailReporter(conf)
    assert r.emails == ['test@mozilla.com', 'test2@mozilla.com', 'test3@mozilla.com']


@responses.activate
def test_mail(mock_config, mock_issues, mock_revision, mock_taskcluster_config):
    '''
    Test mail sending through Taskcluster
    '''
    from static_analysis_bot.report.mail import MailReporter
    from static_analysis_bot.revisions import ImprovementPatch

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
        'http://taskcluster.test/notify/v1/email',
        callback=_check_email,
    )

    # Publish email
    conf = {
        'emails': [
            'test@mozilla.com',
        ],
    }
    r = MailReporter(conf)

    mock_revision.improvement_patches = [
        ImprovementPatch('clang-tidy', repr(mock_revision), 'Some code fixes'),
        ImprovementPatch('clang-format', repr(mock_revision), 'Some lint fixes'),
    ]
    list(map(lambda p: p.write(), mock_revision.improvement_patches))  # trigger local write
    r.publish(mock_issues, mock_revision)

    # Check stats
    mock_cls = mock_issues[0].__class__
    assert r.calc_stats(mock_issues) == {
        mock_cls: {
            'total': 5,
            'publishable': 3,
            'publishable_paths': ['/path/to/file']
        }
    }
