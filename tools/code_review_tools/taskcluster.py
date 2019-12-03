# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime

import requests

TASKCLUSTER_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def create_blob_artifact(
    queue_service, task_id, run_id, path, content, content_type, ttl
):
    """
    Manually create and upload a blob artifact to use a specific content type
    """
    assert isinstance(content, str)
    assert isinstance(ttl, datetime.timedelta)

    # Create S3 artifact on Taskcluster
    # blob artifact has issues on new workers
    resp = queue_service.createArtifact(
        task_id,
        run_id,
        path,
        {
            "storageType": "s3",
            "expires": (datetime.datetime.utcnow() + ttl).strftime(
                TASKCLUSTER_DATE_FORMAT
            ),
            "contentType": content_type,
        },
    )
    assert resp["storageType"] == "s3", "Not an s3 storage"
    assert "putUrl" in resp, "Missing putUrl"
    assert "contentType" in resp, "Missing contentType"

    # Push the artifact on storage service
    headers = {"Content-Type": resp["contentType"]}
    push = requests.put(url=resp["putUrl"], headers=headers, data=content)
    push.raise_for_status()

    # Build the absolute url
    return f"https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/{task_id}/runs/{run_id}/artifacts/{path}"
