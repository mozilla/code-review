# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import importlib
import sys

import pytest


@pytest.fixture
def workflow():
    """Import manually run.py file as we do not use a Python module"""
    spec = importlib.util.spec_from_file_location("run", "run.py")
    run = importlib.util.module_from_spec(spec)
    sys.modules["run"] = run
    spec.loader.exec_module(run)
    return run


@pytest.fixture
def mock_taskcluster(workflow):
    """
    Mock the taskcluster secret
    """
    workflow.taskcluster.secrets = {
        "phabricator": {"url": "http://phab.test/api/", "token": "cli-fakeToken"}
    }
