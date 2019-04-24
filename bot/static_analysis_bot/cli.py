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
from cli_common.phabricator import BuildState
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
    '--id',
    envvar='ANALYSIS_ID',
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
def main(id,
         work_dir,
         taskcluster_secret,
         taskcluster_client_id,
         taskcluster_access_token,
         ):

    secrets = get_secrets(taskcluster_secret,
                          config.PROJECT_NAME,
                          required=(
                              'APP_CHANNEL',
                              'REPORTERS',
                              'ANALYZERS',
                              'PHABRICATOR',
                              'ALLOWED_PATHS',
                              'MAX_CLONE_RUNTIME',
                          ),
                          existing={
                              'APP_CHANNEL': 'development',
                              'REPORTERS': [],
                              'ANALYZERS': [],
                              'PUBLICATION': 'IN_PATCH',
                              'ALLOWED_PATHS': ['*', ],
                              'MAX_CLONE_RUNTIME': 15 * 60,
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
        work_dir,
        secrets['PUBLICATION'],
        secrets['ALLOWED_PATHS'],
        secrets.get('COVERITY_CONFIG'),
        secrets['MAX_CLONE_RUNTIME'],
        phabricator.get('build_plan'),
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
    phabricator_api = PhabricatorAPI(phabricator['api_key'], phabricator['url'])
    if 'phabricator' in reporters:
        reporters['phabricator'].setup_api(phabricator_api)

    # Load unique revision
    if settings.source == SOURCE_PHABRICATOR:
        revision = PhabricatorRevision(phabricator_api, diff_phid=id)
    elif settings.source == SOURCE_TRY:
        revision = PhabricatorRevision(phabricator_api, try_task=queue_service.task(settings.try_task_id))
    else:
        raise Exception('Unsupported source {}'.format(settings.source))

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

        # Update Harbormaster status
        revision.update_status(state=BuildState.Fail)

        # Then raise to mark task as erroneous
        raise


if __name__ == '__main__':
    main()
