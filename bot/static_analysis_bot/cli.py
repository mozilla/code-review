# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os.path
import tempfile

import click

from cli_common.cli import taskcluster_options
from cli_common.log import get_logger
from cli_common.log import init_logger
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import get_secrets
from cli_common.taskcluster import get_service
from static_analysis_bot import AnalysisException
from static_analysis_bot import config
from static_analysis_bot import stats
from static_analysis_bot.config import SOURCE_PHABRICATOR
from static_analysis_bot.config import SOURCE_TRY
from static_analysis_bot.config import settings
from static_analysis_bot.report import get_reporters
from static_analysis_bot.revisions import PhabricatorRevision
from static_analysis_bot.workflows import Workflow

logger = get_logger(__name__)


@click.command()
@taskcluster_options
@click.option(
    '--source',
    envvar='ANALYSIS_SOURCE',
)
@click.option(
    '--id',
    envvar='ANALYSIS_ID',
)
@click.option(
    '--task-id',
    envvar='TASK_ID',
)
@click.option(
    '--work-dir',
    default=os.path.join(
        tempfile.gettempdir(),
        'staticanalysis',
    ),
    help='Work directory, used to pull changesets'
)
@stats.api.timer('runtime.analysis')
def main(source,
         id,
         task_id,
         work_dir,
         taskcluster_secret,
         taskcluster_client_id,
         taskcluster_access_token,
         ):
    assert source in (SOURCE_TRY, SOURCE_PHABRICATOR), \
        'Unsupported analysis source: {}'.format(source)

    secrets = get_secrets(taskcluster_secret,
                          config.PROJECT_NAME,
                          required=(
                              'APP_CHANNEL',
                              'REPORTERS',
                              'ANALYZERS',
                              'PHABRICATOR',
                              'ALLOWED_PATHS',
                          ),
                          existing={
                              'APP_CHANNEL': 'development',
                              'REPORTERS': [],
                              'ANALYZERS': ['clang-tidy', ],
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
    settings.setup(
        secrets['APP_CHANNEL'],
        work_dir,
        source,
        secrets['PUBLICATION'],
        secrets['ALLOWED_PATHS'],
        secrets.get('COVERITY_CONFIG'),
        task_id,
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

    # Local clone available when not running on try
    settings.has_local_clone = source != 'try'

    # Load queue service
    queue_service = get_service(
        'queue',
        taskcluster_client_id,
        taskcluster_access_token,
    )

    # Load Phabricator API
    phabricator_api = PhabricatorAPI(**secrets['PHABRICATOR'])
    if 'phabricator' in reporters:
        reporters['phabricator'].setup_api(phabricator_api)

    # Load unique revision
    revision = PhabricatorRevision(id, phabricator_api)

    # Run workflow according to source
    w = Workflow(reporters, secrets['ANALYZERS'], index_service, queue_service, phabricator_api)
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

        # Then raise to mark task as erroneous
        raise


if __name__ == '__main__':
    main()
