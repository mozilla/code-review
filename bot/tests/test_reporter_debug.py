# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os.path

import responses


@responses.activate
def test_publication(tmpdir, mock_issues, mock_phabricator):
    '''
    Test debug publication and report analysis
    '''
    from static_analysis_bot.report.debug import DebugReporter
    from static_analysis_bot.revisions import PhabricatorRevision

    report_dir = str(tmpdir.mkdir('public').realpath())
    report_path = os.path.join(report_dir, 'report.json')
    assert not os.path.exists(report_path)

    with mock_phabricator as api:
        prev = PhabricatorRevision('PHID-DIFF-abcdef', api)

    r = DebugReporter(report_dir)
    r.publish(mock_issues, prev)

    assert os.path.exists(report_path)
    with open(report_path) as f:
        report = json.load(f)

    assert 'issues' in report
    assert report['issues'] == [{'nb': 0}, {'nb': 1}, {'nb': 2}, {'nb': 3}, {'nb': 4}]

    assert 'revision' in report
    assert report['revision'] == {
        'source': 'phabricator',
        'id': 51,
        'url': 'https://phabricator.test/D51',
        'bugzilla_id': '',
        'diff_phid': 'PHID-DIFF-abcdef',
        'phid': 'PHID-DREV-zzzzz',
        'title': 'Static Analysis tests',
        'has_clang_files': False,
    }

    assert 'time' in report
    assert isinstance(report['time'], float)
