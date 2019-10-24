# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os.path


def test_publication(tmpdir, mock_issues, mock_revision):
    """
    Test debug publication and report analysis
    """
    from code_review_bot.report.debug import DebugReporter

    # Load description from Taskcluster tasks
    mock_revision.setup_try(
        {
            # Base information are retrieved from the decision task
            "decision": {
                "task": {
                    "payload": {
                        "image": "taskcluster/decision",
                        "env": {
                            "GECKO_HEAD_REV": "deadc0ffee",
                            "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                            "GECKO_BASE_REPOSITORY": "https://hg.mozilla.org/mozilla-central",
                        },
                    }
                }
            }
        }
    )

    report_dir = str(tmpdir.mkdir("public").realpath())
    report_path = os.path.join(report_dir, "report.json")
    assert not os.path.exists(report_path)

    r = DebugReporter(report_dir)
    r.publish(mock_issues, mock_revision)

    assert os.path.exists(report_path)
    with open(report_path) as f:
        report = json.load(f)

    assert "issues" in report
    assert report["issues"] == [{"nb": 0}, {"nb": 1}, {"nb": 2}, {"nb": 3}, {"nb": 4}]

    assert "revision" in report
    assert report["revision"] == {
        "id": 51,
        "diff_id": 42,
        "url": "https://phabricator.test/D51",
        "bugzilla_id": 1234567,
        "diff_phid": "PHID-DIFF-test",
        "phid": "PHID-DREV-zzzzz",
        "title": "Static Analysis tests",
        "has_clang_files": False,
        "repository": "try",
        "target_repository": "mozilla-central",
        "mercurial_revision": "deadc0ffee",
    }

    assert "time" in report
    assert isinstance(report["time"], float)
