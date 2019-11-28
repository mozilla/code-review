# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Heroku Documentation: https://devcenter.heroku.com/articles/dynos#local-environment-variables

import os


def in_dyno():
    """Detects if the process is running in an Heroku Dyno"""
    return "DYNO" in os.environ


def in_web_dyno():
    """Detects if the process is running in an Heroku web Dyno"""
    return "PORT" in os.environ and os.environ.get("DYNO", "").startswith("web.")


def in_worker_dyno():
    """Detects if the process is running in an Heroku web Dyno"""
    return os.environ.get("DYNO", "").startswith("worker.")
