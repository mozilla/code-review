from urllib.parse import urlencode

JOBS_URL = "https://treeherder.mozilla.org/#/jobs"


def get_job_url(repository, revision, task_id=None, run_id=None, **params):
    """Build a Treeherder job url for a given Taskcluster task"""
    assert isinstance(repository, str) and repository, "Missing repository"
    assert isinstance(revision, str) and revision, "Missing revision"
    assert "repo" not in params, "repo cannot be set in params"
    assert "revision" not in params, "revision cannot be set in params"

    params.update({"repo": repository, "revision": revision})

    if task_id is not None and run_id is not None:
        params["selectedTaskRun"] = f"{task_id}-{run_id}"

    return f"{JOBS_URL}?{urlencode(params)}"
