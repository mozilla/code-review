#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import re
import shutil
import subprocess

import structlog
import yaml
from taskcluster.helper import TaskclusterConfig

taskcluster = TaskclusterConfig("https://community-tc.services.mozilla.com")

logger = structlog.getLogger(__name__)

ROOT = os.path.realpath(os.path.dirname(__file__))


def configure():
    """
    Load configuration from CLI args and Taskcluster secrets
    """
    parser = argparse.ArgumentParser(description="Run code-review integration tests")
    parser.add_argument(
        "-c",
        "--configuration",
        help="Local configuration file replacing Taskcluster secrets",
        type=open,
    )
    parser.add_argument(
        "--clone-dir",
        help="Directory where to clone repositories",
        default=os.environ.get("CLONE_DIR", os.path.join(ROOT, "clone")),
    )
    parser.add_argument(
        "--taskcluster-secret",
        help="Taskcluster Secret path",
        default=os.environ.get("TASKCLUSTER_SECRET"),
    )
    args = parser.parse_args()

    taskcluster.auth()
    taskcluster.load_secrets(
        args.taskcluster_secret,
        required=("phabricator", "admins"),
        existing={"admins": ["babadie@mozilla.com"]},
        local_secrets=yaml.safe_load(args.configuration)
        if args.configuration
        else None,
    )

    # Make sure the clone dir is available
    os.makedirs(args.clone_dir, exist_ok=True)

    # Check the url is correctly formatted
    assert taskcluster.secrets["phabricator"]["url"].endswith(
        "/api/"
    ), "Phabricator url must end in /api/"

    return args


def clone(url, directory, branch="tip"):
    """
    Mercurial clone with robustcheckout
    """
    logger.info("Cloning repository", url=url, dir=directory)

    # Parent should exist, not current dir
    assert os.path.exists(os.path.dirname(directory)), "Missing parent of clone dir"

    # Cleanup existing target
    if os.path.exists(directory):
        logger.info("Removing previous clone")
        shutil.rmtree(directory)

    # Now let's clone
    cmd = [
        "hg",
        "robustcheckout",
        "--purge",
        f"--sharebase={directory}-shared",
        f"--branch={branch}",
        url,
        directory,
    ]
    subprocess.check_output(cmd)


def tip(repo_dir):
    """
    Get the tip of the repo
    """
    cmd = ["hg", "tip", "--template={rev}"]
    rev = subprocess.check_output(cmd, cwd=repo_dir)
    return int(rev)


def patch(filename, repo_dir, message):
    """
    Apply a locally stored patch on the repository
    and commit the difference
    """
    assert os.path.isdir(repo_dir), f"Not a directory {repo_dir}"
    path = os.path.join(ROOT, "patches", filename)
    assert os.path.exists(path), f"Missing patch {path}"

    logger.info("Applying patch", name=filename, dir=repo_dir)
    cmd = [
        "hg",
        "import",
        "--user=code-review-integration",
        f"--message={message}",
        path,
    ]
    subprocess.check_output(cmd, cwd=repo_dir)

    # Load revision created
    rev = tip(repo_dir)
    logger.info("Committed a new revision", id=rev)
    return rev


def publish(repo_dir, repo_callsign, revision):
    """
    Publish diff on Phabricator
    from the base of the repository
    """

    def _dump(path, payload):
        if os.path.exists(path):
            logger.info("Skip overriding arc config", path=path)
            return

        with open(path, "w") as f:
            json.dump(payload, f, indent=4, sort_keys=True)
            logger.info("Setup arc configuration", path=path)

    # Write arcrc config files
    phab_url = taskcluster.secrets["phabricator"]["url"]
    base_url = phab_url.replace("/api/", "/")
    phab_token = taskcluster.secrets["phabricator"]["token"]
    _dump(os.path.expanduser("~/.arcrc"), {"hosts": {phab_url: {"token": phab_token}}})
    _dump(
        os.path.join(repo_dir, ".hg", ".arcconfig"),
        {"repository.callsign": repo_callsign, "phabricator.uri": base_url},
    )

    logger.info(
        "Publishing a revision on phabricator", url=phab_url, local_revision=revision
    )
    cmd = [
        "moz-phab",
        "submit",
        "--yes",
        "--no-lint",
        "--no-bug",
        "--no-arc",
        f"{revision}",
    ]
    output = subprocess.check_output(cmd, cwd=repo_dir)

    # Parse output to get the revision url on the last line
    last_line = output.splitlines()[-1]
    match = re.search(fr"^-> ({base_url}D\d+)$", last_line.decode("utf-8"))
    assert match is not None, f"No revision found in moz-phab output:\n{output}"

    return match.group(1)


def notify(message):
    """
    Notify admins through email
    """
    notify = taskcluster.get_service("notify")
    for email in taskcluster.secrets["admins"]:
        logger.info("Sending email", to=email)
        notify.email(
            {
                "address": email,
                "subject": "Code review integration test",
                "content": message,
            }
        )


if __name__ == "__main__":
    logger.info("Running integration test")
    args = configure()

    # Clone NSS for a shorter time than MC
    nss = os.path.join(args.clone_dir, "nss")
    clone("https://hg.mozilla.org/projects/nss", nss)
    base = tip(nss)

    # Apply a specific patch on the NSS clone
    revision = patch("nss.diff", nss, "Bug XXYYZZ - Code review integration test")

    # Submit commit on Phabricator instance
    url = publish(nss, "NSS", revision)

    # Send notification to admins
    notify(f"New code-review integration test: {url}")

    logger.info("All done !")
