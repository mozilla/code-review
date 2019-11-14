# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import datetime
import os

import requests
import structlog
import taskcluster
import toml
import yaml

logger = structlog.get_logger(__name__)

TASKCLUSTER_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class TaskclusterConfig(object):
    """
    Local configuration used to access Taskcluster service and objects
    """

    def __init__(self):
        self.options = None
        self.secrets = None

    def auth(self, client_id=None, access_token=None):
        """
        Build Taskcluster credentials options
        Supports, by order of preference:
         * directly provided credentials
         * credentials from local configuration
         * credentials from environment variables
         * taskclusterProxy
        """
        self.options = {"maxRetries": 12}
        default_taskcluster_url = os.environ.get(
            "TASKCLUSTER_ROOT_URL", "https://firefox-ci-tc.services.mozilla.com"
        )

        if client_id is None and access_token is None:
            # Credentials preference: Use local config from release-services
            xdg = os.path.expanduser(os.environ.get("XDG_CONFIG_HOME", "~/.config"))
            config = os.path.join(xdg, "please", "config.toml")
            try:
                assert os.path.exists(config), "No user config available"
                data = toml.load(open(config))
                client_id = data["common"]["taskcluster_client_id"]
                access_token = data["common"]["taskcluster_access_token"]
                assert (
                    client_id is not None and access_token is not None
                ), "Missing values in user folder"
                logger.info("Using taskcluster credentials from local configuration")
            except Exception:
                # Credentials preference: Use env. variables
                client_id = os.environ.get("TASKCLUSTER_CLIENT_ID")
                access_token = os.environ.get("TASKCLUSTER_ACCESS_TOKEN")
                logger.info("Using taskcluster credentials from environment")
        else:
            logger.info("Using taskcluster credentials from cli")

        if client_id is not None and access_token is not None:
            # Use provided credentials
            self.options["credentials"] = {
                "clientId": client_id,
                "accessToken": access_token,
            }
            self.options["rootUrl"] = default_taskcluster_url

        elif "TASK_ID" in os.environ:
            # Load secrets from TC task context
            # with taskclusterProxy
            # Only works when running in a Taskcluster Task
            logger.info("Taskcluster Proxy enabled")
            self.options["rootUrl"] = "http://taskcluster"

        else:
            logger.info("No Taskcluster authentication.")
            self.options["rootUrl"] = default_taskcluster_url

    def get_service(self, service_name):
        """
        Build a Taskcluster service instance using current authentication
        """
        assert self.options is not None, "Not authenticated"
        service = getattr(taskcluster, service_name.capitalize(), None)
        assert service is not None, "Invalid Taskcluster service {}".format(
            service_name
        )
        return service(self.options)

    def load_secrets(
        self, name, project_name, required=[], existing=dict(), local_source=None
    ):
        """
        Fetch a specific set of secrets by name and verify that the required
        secrets exist.
        Also supports a local YAML file through local_source (file descriptor)

        Merge secrets in the following order (the latter overrides the former):
            - `existing` argument
            - common secrets, specified under the `common` key in the secrets
              object
            - project specific secrets, specified under the `project_name` key in
              the secrets object
        """
        self.secrets = dict()
        if existing:
            self.secrets = copy.deepcopy(existing)

        if local_source is None:
            # Use Taskcluster secret service
            assert name is not None, "Missing Taskcluster secret name"
            secrets_service = self.get_service("secrets")
            all_secrets = secrets_service.get(name).get("secret", dict())
            logger.info("Loaded Taskcluster secret", name=name)
        else:
            # Use local YAML file to avoid using Taskcluster secrets
            logger.info(f"Using local secrets from {local_source.name}")
            all_secrets = yaml.safe_load(local_source)

        secrets_common = all_secrets.get("common", dict())
        self.secrets.update(secrets_common)

        secrets_app = all_secrets.get(project_name, dict())
        self.secrets.update(secrets_app)

        for required_secret in required:
            if required_secret not in self.secrets:
                raise Exception(f"Missing value {required_secret} in secrets.")


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
