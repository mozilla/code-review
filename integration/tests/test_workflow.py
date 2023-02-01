# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import subprocess


def test_publish(monkeypatch, workflow, tmpdir, mock_taskcluster):
    # Fake repo
    repo_dir = tmpdir.realpath()
    hg = tmpdir.mkdir(".hg")

    # Fake moz-phab
    def moz_phab(cmd, **kwargs):
        assert cmd == ["moz-phab", "submit", "--yes", "--no-lint", "--no-bug", "1234"]
        assert kwargs == {"cwd": repo_dir}

        return b"some random output...\n-> http://phab.test/D1"

    monkeypatch.setattr(subprocess, "check_output", moz_phab)

    # Run publication
    revision_url = workflow.publish(repo_dir, "TEST", 1234)
    assert revision_url == "http://phab.test/D1"

    # Check the arc auth is setup
    arcconfig = json.loads(hg.join(".arcconfig").read())
    assert arcconfig == {
        "phabricator.uri": "http://phab.test/",
        "repository.callsign": "TEST",
    }
