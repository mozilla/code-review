# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import urllib.parse
from datetime import timedelta

import requests
import structlog
import tenacity
from libmozdata.phabricator import PhabricatorAPI
from parsepatch.patch import Patch

from code_review_bot import Issue
from code_review_bot import stats
from code_review_bot import taskcluster
from code_review_bot.config import REGEX_PHABRICATOR_COMMIT
from code_review_bot.config import REPO_AUTOLAND
from code_review_bot.config import REPO_MOZILLA_CENTRAL
from code_review_bot.config import settings

logger = structlog.get_logger(__name__)


@tenacity.retry(wait=tenacity.wait_incrementing(start=5, increment=4))
def hgmo_build_phid(repository, revision):
    """
    Retrieve the Phabricator build PHID from a try_task_config.json
    file on a remote mercurial repository on HGMO
    """
    resp = requests.get(f"{repository}/raw-file/{revision}/try_task_config.json")
    resp.raise_for_status()
    config = resp.json()

    assert config.get("version") == 2, "Invalid try task config version"
    parameters = config.get("parameters")
    assert parameters is not None, "Missing parameters"
    if "phabricator_diff" in parameters:
        return parameters["phabricator_diff"]
    elif "code-review" in parameters:
        return parameters["code-review"]["phabricator-build-target"]
    else:
        raise Exception("Unsupported try_task_config json payload")


class ImprovementPatch(object):
    """
    An improvement patch built by the bot
    """

    def __init__(self, analyzer_name, patch_name, content):
        # Build name from analyzer and revision
        self.analyzer = analyzer_name
        self.name = "{}-{}.diff".format(analyzer_name, patch_name)
        self.content = content
        self.url = None
        self.path = None

    def __str__(self):
        return "{}: {}".format(self.analyzer, self.url or self.path or self.name)

    def write(self):
        """
        Write patch on local FS, for dev & tests only
        """
        self.path = os.path.join(settings.taskcluster.results_dir, self.name)
        with open(self.path, "w") as f:
            length = f.write(self.content)
            logger.info("Improvement patch saved", path=self.path, length=length)

    def publish(self, days_ttl=30):
        """
        Push through Taskcluster API to setup the content-type header
        so it displays nicely in browsers
        """
        assert (
            not settings.taskcluster.local
        ), "Only publish on online Taskcluster tasks"
        self.url = taskcluster.upload_artifact(
            "public/patch/{}".format(self.name),
            self.content,
            content_type="text/plain; charset=utf-8",  # Displays instead of download
            ttl=timedelta(days=days_ttl - 1),
        )
        logger.info("Improvement patch published", url=self.url)


class Revision(object):
    """
    A Phabricator revision to analyze and report on
    """

    def __init__(
        self,
        id,
        phid=None,
        diff_id=None,
        diff_phid=None,
        revision=None,
        diff=None,
        build_target_phid=None,
        mercurial_revision=None,
        repository=None,
        repository_try_name=None,
        target_repository=None,
        url=None,
        patch=None,
    ):

        # Identification
        self.id = id
        self.phid = phid
        self.diff_id = diff_id
        self.diff_phid = diff_phid
        self.build_target_phid = build_target_phid
        self.mercurial_revision = mercurial_revision
        self.revision = revision
        self.diff = diff
        self.url = url

        # a try repo where the revision is stored
        self.repository = repository

        # the name of the try repo where the revision is stored
        self.repository_try_name = repository_try_name

        # the target repo where the patch may land
        self.target_repository = target_repository

        # Backend data
        self.issues_url = None

        # Patches built later on
        self.improvement_patches = []

        # Patch analysis
        self.patch = patch
        self.files = []
        self.lines = {}

    @property
    def namespaces(self):
        return [
            "phabricator.{}".format(self.id),
            "phabricator.diff.{}".format(self.diff_id),
            "phabricator.phid.{}".format(self.phid),
            "phabricator.diffphid.{}".format(self.diff_phid),
        ]

    def __repr__(self):
        return self.diff_phid

    def __str__(self):
        return "Phabricator #{} - {}".format(self.diff_id, self.diff_phid)

    @staticmethod
    def from_try(try_decision_task: dict, phabricator: PhabricatorAPI):
        """
        Load identifiers from Phabricator, using the remote task description
        """
        logger.info(
            "Using try decision task", name=try_decision_task["metadata"]["name"]
        )

        def match_task_env(repository):
            decision_env = try_decision_task["payload"]["env"]
            try_url = repository.try_url.replace("ssh://", "https://")

            if repository.decision_env_revision not in decision_env:
                return
            if repository.decision_env_repository not in decision_env:
                return
            if try_url != decision_env[repository.decision_env_repository]:
                return

            return {
                "repository": decision_env[repository.decision_env_repository],
                "target_repository": repository.url,
                "mercurial_revision": decision_env[repository.decision_env_revision],
            }

        # Match the supported repositories from settings
        # with the decision task environment to get the mercurial information
        hg_config = next(
            filter(
                None,
                (match_task_env(repository) for repository in settings.repositories),
            ),
            None,
        )

        # Check mercurial revision is set
        assert hg_config is not None, "Unsupported decision task"
        logger.info("Using mercurial revision", **hg_config)

        # Load build target phid from the HGMO server
        build_target_phid = hgmo_build_phid(
            hg_config["repository"], hg_config["mercurial_revision"]
        )
        assert build_target_phid.startswith(
            "PHID-HMBT-"
        ), "Not a Phabricator build phid"

        # And get the diff from the phabricator api
        buildable = phabricator.find_target_buildable(build_target_phid)
        diff_phid = buildable["fields"]["objectPHID"]
        assert diff_phid.startswith("PHID-DIFF-")

        # Load diff details to get the diff revision
        # We also load the commits list in order to get the email of the author of the
        # patch for sending email if builds are failing.
        diffs = phabricator.search_diffs(
            diff_phid=diff_phid, attachments={"commits": True}
        )
        assert len(diffs) == 1, "No diff available for {}".format(diff_phid)
        diff = diffs[0]
        diff_id = diff["id"]
        phid = diff["revisionPHID"]

        revision = phabricator.load_revision(phid)

        # Load target patch from Phabricator for Try mode
        patch = phabricator.load_raw_diff(diff_id)

        # Build a revision without repositories as they are retrieved later
        # when analyzing the full task group
        return Revision(
            id=revision["id"],
            phid=phid,
            diff_id=diff_id,
            diff_phid=diff_phid,
            build_target_phid=build_target_phid,
            revision=revision,
            diff=diff,
            url="https://{}/D{}".format(phabricator.hostname, revision["id"]),
            patch=patch,
            **hg_config,
        )

    @staticmethod
    def from_autoland(autoland_task: dict, phabricator: PhabricatorAPI):
        """
        Build a revision from a Mozilla autoland decision task
        """
        assert (
            autoland_task["payload"]["env"]["GECKO_HEAD_REPOSITORY"] == REPO_AUTOLAND
        ), "Not an autoland decision task"

        # Load mercurial revision
        mercurial_revision = autoland_task["payload"]["env"]["GECKO_HEAD_REV"]

        # Search phabricator revision from commit message
        commit_url = (
            f"https://hg.mozilla.org/integration/autoland/json-rev/{mercurial_revision}"
        )
        response = requests.get(commit_url)
        response.raise_for_status()
        description = response.json()["desc"]
        match = REGEX_PHABRICATOR_COMMIT.search(description)
        if match is not None:
            url, revision_id = match.groups()
            revision_id = int(revision_id)
            logger.info("Found phabricator revision", id=revision_id, url=url)
        else:
            raise Exception(f"No phabricator revision found in commit {commit_url}")

        # Lookup the Phabricator revision to get details (phid, title, bugzilla_id, ...)
        revision = phabricator.load_revision(rev_id=revision_id)

        # Search the Phabricator diff with same commit identifier
        diffs = phabricator.search_diffs(
            revision_phid=revision["phid"], attachments={"commits": True}
        )
        diff = next(
            iter(
                d
                for d in diffs
                if d["attachments"]["commits"]["commits"][0]["identifier"]
                == mercurial_revision
            ),
            None,
        )
        assert (
            diff is not None
        ), f"No Phabricator diff found for D{revision_id} and mercurial revision {mercurial_revision}"
        logger.info("Found phabricator diff", id=diff["id"])

        return Revision(
            id=revision_id,
            phid=revision["phid"],
            diff_id=diff["id"],
            diff_phid=diff["phid"],
            mercurial_revision=mercurial_revision,
            repository=REPO_AUTOLAND,
            target_repository=REPO_MOZILLA_CENTRAL,
            revision=revision,
            diff=diff,
            url=url,
        )

    def analyze_patch(self):
        """
        Analyze loaded patch to extract modified lines
        and statistics
        """
        assert self.patch is not None, "Missing patch"
        assert isinstance(self.patch, str), "Invalid patch type"

        # List all modified lines from current revision changes
        patch = Patch.parse_patch(self.patch, skip_comments=False)
        assert patch != {}, "Empty patch"
        self.lines = {
            # Use all changes in new files
            filename: diff.get("touched", []) + diff.get("added", [])
            for filename, diff in patch.items()
        }

        # Shortcut to files modified
        self.files = self.lines.keys()

        # Report nb of files and lines analyzed
        stats.add_metric("analysis.files", len(self.files))
        stats.add_metric(
            "analysis.lines", sum(len(line) for line in self.lines.values())
        )

    def load_file(self, path):
        """
        Load a file content at current revision from remote HGMO
        """
        # Check in hgmo cache first
        cache_path = os.path.join(settings.hgmo_cache, path)
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                return f.read()

        # Retrieve remote file
        url = urllib.parse.urljoin(
            "https://hg.mozilla.org",
            f"{self.repository}/raw-file/{self.mercurial_revision}/{path}",
        )
        logger.info("Downloading HGMO file", url=url)
        response = requests.get(url)
        response.raise_for_status()

        # Store in cache
        content = response.content.decode("utf-8")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(content)

        return content

    def has_file(self, path):
        """
        Check if the path is in this patch
        """
        assert isinstance(path, str)
        return path in self.files

    def contains(self, issue):
        """
        Check if the issue (path+lines) is in this patch
        """
        assert isinstance(issue, Issue)

        # Get modified lines for this issue
        modified_lines = self.lines.get(issue.path)
        if modified_lines is None:
            logger.warn("Issue path is not in revision", path=issue.path, revision=self)
            return False

        # Empty line means full file
        if issue.line is None:
            return True

        # Detect if this issue is in the patch
        lines = set(range(issue.line, issue.line + issue.nb_lines))
        return not lines.isdisjoint(modified_lines)

    @property
    def has_clang_files(self):
        """
        Check if this revision has any file that might
        be a C/C++ file
        """

        def _is_clang(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.cpp_extensions

        return any(_is_clang(f) for f in self.files)

    @property
    def has_clang_header_files(self):
        """
        Check if this revision has any file that might
        be a C/C++ header file
        """

        def _is_clang_header(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.cpp_header_extensions

        return any(_is_clang_header(f) for f in self.files)

    @property
    def has_idl_files(self):
        """
        Check if this revision has any idl files
        """

        def _is_idl(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.idl_extensions

        return any(_is_idl(f) for f in self.files)

    @property
    def has_infer_files(self):
        """
        Check if this revision has any file that might
        be a Java file
        """

        def _is_infer(filename):
            _, ext = os.path.splitext(filename)
            return ext.lower() in settings.java_extensions

        return any(_is_infer(f) for f in self.files)

    def add_improvement_patch(self, analyzer_name, content):
        """
        Save an improvement patch, and make it available
        as a Taskcluster artifact
        """
        assert isinstance(content, str)
        assert len(content) > 0
        self.improvement_patches.append(
            ImprovementPatch(analyzer_name, repr(self), content)
        )

    def reset(self):
        """
        Reset temporary data in BEFORE mode
        * improvement patches
        """
        self.improvement_patches = []

    @property
    def bugzilla_id(self):
        if self.revision is None:
            return None
        try:
            return int(self.revision["fields"].get("bugzilla.bug-id"))
        except (TypeError, ValueError):
            logger.info("No bugzilla id available for this revision")
            return None

    @property
    def title(self):
        if self.revision is None:
            return None
        return self.revision["fields"].get("title")

    def as_dict(self):
        """
        Outputs a serializable representation of this revision
        """
        return {
            "diff_phid": self.diff_phid,
            "phid": self.phid,
            "diff_id": self.diff_id,
            "id": self.id,
            "url": self.url,
            "has_clang_files": self.has_clang_files,
            # Extra infos for frontend
            "title": self.title,
            "bugzilla_id": self.bugzilla_id,
            # Extra infos for backend
            "repository": self.repository,
            "target_repository": self.target_repository,
            "mercurial_revision": self.mercurial_revision,
        }
