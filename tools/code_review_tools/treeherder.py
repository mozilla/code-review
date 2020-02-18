# -*- coding: utf-8 -*-

from urllib.parse import urlencode

import slugid
from thclient import TreeherderClient

JOBS_URL = "https://treeherder.mozilla.org/#/jobs"


def get_job_url(task_id, run_id, **params):
    """Build a Treeherder job url for a given Taskcluster task"""
    treeherder_client = TreeherderClient()
    uuid = slugid.decode(task_id)

    # Fetch specific job id from treeherder
    job_details = treeherder_client.get_job_details(job_guid=f"{uuid}/{run_id}")
    if len(job_details) > 0:
        params["selectedJob"] = job_details[0]["job_id"]

    return f"{JOBS_URL}?{urlencode(params)}"


def get_revision_url(repository, revision):
    """Build a Treeherder job url for a given revision"""
    assert isinstance(repository, str) and repository, "Missing repository"
    assert isinstance(revision, str) and revision, "Missing revision"
    params = {"repo": repository, "revision": revision}
    return f"{JOBS_URL}?{urlencode(params)}"
