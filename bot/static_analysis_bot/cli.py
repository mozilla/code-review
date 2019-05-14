# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import click

from cli_common.cli import taskcluster_options
from cli_common.log import get_logger
from cli_common.log import init_logger
from cli_common.phabricator import BuildState
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import get_secrets
from cli_common.taskcluster import get_service
from static_analysis_bot import AnalysisException
from static_analysis_bot import config
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.report import get_reporters
from static_analysis_bot.revisions import Revision
from static_analysis_bot.workflow import Workflow

logger = get_logger(__name__)


@click.command()
@taskcluster_options
@stats.api.timer('runtime.analysis')
def main(taskcluster_secret,
         taskcluster_client_id,
         taskcluster_access_token,
         ):

    secrets = get_secrets(taskcluster_secret,
                          config.PROJECT_NAME,
                          required=(
                              'APP_CHANNEL',
                              'REPORTERS',
                              'PHABRICATOR',
                              'ALLOWED_PATHS',
                          ),
                          existing={
                              'APP_CHANNEL': 'development',
                              'REPORTERS': [],
                              'PUBLICATION': 'IN_PATCH',
                              'ALLOWED_PATHS': ['*', ],
                          },
                          taskcluster_client_id=taskcluster_client_id,
                          taskcluster_access_token=taskcluster_access_token,
                          )

    init_logger(config.PROJECT_NAME,
                PAPERTRAIL_HOST=secrets.get('PAPERTRAIL_HOST'),
                PAPERTRAIL_PORT=secrets.get('PAPERTRAIL_PORT'),
                SENTRY_DSN=secrets.get('SENTRY_DSN'),
                MOZDEF=secrets.get('MOZDEF'),
                timestamp=True,
                )

    # Setup settings before stats
    phabricator = secrets['PHABRICATOR']
    settings.setup(
        secrets['APP_CHANNEL'],
        secrets['PUBLICATION'],
        secrets['ALLOWED_PATHS'],
    )
    # Setup statistics
    datadog_api_key = secrets.get('DATADOG_API_KEY')
    if datadog_api_key:
        stats.auth(datadog_api_key)

    # Load reporters
    reporters = get_reporters(
        secrets['REPORTERS'],
        taskcluster_client_id,
        taskcluster_access_token,
    )

    # Load index service
    index_service = get_service(
        'index',
        taskcluster_client_id,
        taskcluster_access_token,
    )

    # Load queue service
    queue_service = get_service(
        'queue',
        taskcluster_client_id,
        taskcluster_access_token,
    )

    # Load Phabricator API
    phabricator_reporting_enabled = 'phabricator' in reporters
    phabricator_api = PhabricatorAPI(phabricator['api_key'], phabricator['url'])
    if phabricator_reporting_enabled:
        reporters['phabricator'].setup_api(phabricator_api)

    # Load unique revision
    revision = Revision(
        phabricator_api,
        try_task=queue_service.task(settings.try_task_id),

        # Update build status only when phabricator reporting is enabled
        update_build=phabricator_reporting_enabled,
    )

    # Run workflow according to source
    w = Workflow(reporters, index_service, queue_service, phabricator_api)
    try:
        w.run(revision)
    except Exception as e:
        # Log errors to papertrail
        logger.error(
            'Static analysis failure',
            revision=revision,
            error=e,
        )

        # Index analysis state
        extras = {}
        if isinstance(e, AnalysisException):
            extras['error_code'] = e.code
            extras['error_message'] = str(e)
        w.index(revision, state='error', **extras)

        # Update Harbormaster status
        revision.update_status(state=BuildState.Fail)

        # Then raise to mark task as erroneous
        raise


if __name__ == '__main__':
    main()
