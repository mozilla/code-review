# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from static_analysis_bot.report.mail import MailReporter
from static_analysis_bot.report.phabricator import PhabricatorReporter

logger = structlog.get_logger(__name__)


def get_reporters(configuration):
    '''
    Load reporters using Taskcluster configuration
    '''
    assert isinstance(configuration, list)
    reporters = {
        'mail': MailReporter,
        'phabricator': PhabricatorReporter,
    }
    out = {}
    for conf in configuration:
        try:
            if 'reporter' not in conf:
                raise Exception('Missing reporter declaration')
            name = conf['reporter']
            cls = reporters.get(name)
            if cls is None:
                raise Exception('Missing reporter class {}'.format(conf['reporter']))
            out[name] = cls(conf)
        except Exception as e:
            logger.warning('Failed to create reporter: {}'.format(e))

    return out
