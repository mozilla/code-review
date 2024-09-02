# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import random
import urllib.parse
from datetime import timedelta
from pathlib import Path

import requests
import rs_parsepatch
import structlog
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue, stats, taskcluster
from code_review_bot.config import (
    REPO_AUTOLAND,
    REPO_MOZILLA_CENTRAL,
    GetAppUserAgent,
    settings,
)
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)


class ImprovementPatch:
    """
    An improvement patch built by the bot
    """

    def __init__(self, analyzer, patch_name, content):
        assert isinstance(analyzer, AnalysisTask)

        # Build name from analyzer and revision
        self.analyzer = analyzer
        self.name = f"{self.analyzer.name}-{patch_name}.diff"
        self.content = content
        self.url = None
        self.path = None

    def __str__(self):
        return f"{self.analyzer.name}: {self.url or self.path or self.name}"

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
            f"public/patch/{self.name}",
            self.content.encode(),
            content_type="text/plain; charset=utf-8",  # Displays instead of download
            ttl=timedelta(days=days_ttl - 1),
        )
        logger.info("Improvement patch published", url=self.url)


class Revision:
    """
    A Phabricator revision to analyze and report on
    """

    def __init__(
        self,
        phabricator_id=None,
        phabricator_phid=None,
        diff_id=None,
        diff_phid=None,
        revision=None,
        diff=None,
        build_target_phid=None,
        head_changeset=None,
        base_changeset=None,
        head_repository=None,
        repository_try_name=None,
        base_repository=None,
        phabricator_repository=None,
        url=None,
        patch=None,
    ):
        # Identification
        self.phabricator_id = phabricator_id
        self.phabricator_phid = phabricator_phid
        self.diff_id = diff_id
        self.diff_phid = diff_phid
        self.build_target_phid = build_target_phid
        self.head_changeset = head_changeset
        self.base_changeset = base_changeset
        self.revision = revision
        self.diff = diff
        self.url = url

        # a try repo where the revision is stored
        self.head_repository = head_repository

        # the name of the try repo where the revision is stored
        self.repository_try_name = repository_try_name

        # the target repo where the patch may land
        self.base_repository = base_repository

        # the phabricator repository payload for later identification
        self.phabricator_repository = phabricator_repository

        # backend's returned URL to list or create issues on the revision's diff
        self.diff_issues_url = None
        # backend's returned URL to list or create issues linked to the revision in bulk (diff is optional)
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
            f"phabricator.{self.phabricator_id}",
            f"phabricator.diff.{self.diff_id}",
            f"phabricator.phabricator_phid.{self.phabricator_phid}",
            f"phabricator.diffphid.{self.diff_phid}",
        ]

    @property
    def before_after_feature(self):
        """
        Randomly run the before/after feature depending on a configured ratio.
        All the diffs of a revision must be analysed with or without the feature.
        """
        if getattr(self, "id", None) is None:
            logger.debug(
                "Backend ID must be set to determine if using the before/after feature. Skipping."
            )
            return False
        # Set random module pseudo-random seed based on the revision ID to
        # ensure that successive calls to random.random will return deterministic values
        random.seed(self.id)
        return random.random() < taskcluster.secrets.get("BEFORE_AFTER_RATIO", 0)
        # Reset random module seed to prevent deterministic values after calling that function
        random.seed(os.urandom(128))

    def __repr__(self):
        return self.diff_phid

    def __str__(self):
        return f"Phabricator #{self.diff_id} - {self.diff_phid}"

    @staticmethod
    def from_try_task(try_task: dict, decision_task: dict, phabricator: PhabricatorAPI):
        """
        Load identifiers from Phabricator, using the remote task description
        """

        # Load build target phid from the task env
        code_review = try_task["extra"]["code-review"]
        build_target_phid = code_review.get("phabricator-diff") or code_review.get(
            "phabricator-build-target"
        )
        assert (
            build_target_phid is not None
        ), "Missing phabricator-build-target or phabricator-diff declaration"
        assert build_target_phid.startswith("PHID-HMBT-")

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
        assert len(diffs) == 1, f"No diff available for {diff_phid}"
        diff = diffs[0]
        diff_id = diff["id"]
        phid = diff["revisionPHID"]

        revision = phabricator.load_revision(phid)

        # Load repository detailed information
        repos = phabricator.request(
            "diffusion.repository.search",
            constraints={"phids": [revision["fields"]["repositoryPHID"]]},
        )
        assert len(repos["data"]) == 1, "Repository not found on Phabricator"

        # Load target patch from Phabricator for Try mode
        patch = phabricator.load_raw_diff(diff_id)

        # The parent decision task should exist
        assert decision_task is not None, "Missing parent decision task"
        logger.info("Found decision task", name=decision_task["metadata"]["name"])

        # Match the decision task environment to get the mercurial information
        decision_env = decision_task["payload"]["env"]
        head_repository = base_repository = head_changeset = base_changeset = (
            repository_try_name
        ) = None
        for prefix in settings.decision_env_prefixes:
            head_repository_key = f"{prefix}_HEAD_REPOSITORY"
            base_repository_key = f"{prefix}_BASE_REPOSITORY"
            head_changeset_key = f"{prefix}_HEAD_REV"
            base_changeset_key = f"{prefix}_BASE_REV"
            if (
                head_repository_key not in decision_env
                or base_repository_key not in decision_env
                or head_changeset_key not in decision_env
                or base_changeset_key not in decision_env
            ):
                continue

            head_repository = decision_env[head_repository_key]
            base_repository = decision_env[base_repository_key]
            head_changeset = decision_env[head_changeset_key]
            base_changeset = decision_env[base_changeset_key]
            repository_try_name = (
                urllib.parse.urlparse(head_repository)
                .path.rstrip("/")
                .rsplit("/", 1)[-1]
            )
            break

        # Check mercurial information were properly retrieved
        assert all(
            attr is not None
            for attr in [
                head_repository,
                base_repository,
                head_changeset,
                base_changeset,
            ]
        ), "Unsupported parent decision task, missing mercurial information in its environment"
        logger.info(
            "Using mercurial changeset",
            head_changeset=head_changeset,
            head_repository=head_repository,
            base_repository=base_repository,
        )

        # Build a revision without repositories as they are retrieved later
        # when analyzing the full task group
        return Revision(
            phabricator_id=revision["id"],
            phabricator_phid=phid,
            diff_id=diff_id,
            diff_phid=diff_phid,
            build_target_phid=build_target_phid,
            revision=revision,
            phabricator_repository=repos["data"][0],
            diff=diff,
            url="https://{}/D{}".format(phabricator.hostname, revision["id"]),
            patch=patch,
            head_changeset=head_changeset,
            base_changeset=base_changeset,
            head_repository=head_repository,
            repository_try_name=repository_try_name,
            base_repository=base_repository,
        )

    @staticmethod
    def from_decision_task(task: dict, phabricator: PhabricatorAPI):
        """
        Build a revision from a Mozilla decision task (e.g. from Autoland or Mozilla-central).
        No Phabricator reference nor diff is saved.
        """
        # Load repositories
        head_repository = task["payload"]["env"]["GECKO_HEAD_REPOSITORY"]
        base_repository = task["payload"]["env"]["GECKO_BASE_REPOSITORY"]

        assert head_repository in (
            REPO_AUTOLAND,
            REPO_MOZILLA_CENTRAL,
        ), "Decision task must be on autoland or mozilla-central"

        # Load mercurial changesets
        head_changeset = task["payload"]["env"]["GECKO_HEAD_REV"]
        base_changeset = task["payload"]["env"]["GECKO_BASE_REV"]

        return Revision(
            head_changeset=head_changeset,
            base_changeset=base_changeset,
            head_repository=head_repository,
            base_repository=base_repository,
        )

    def analyze_patch(self):
        """
        Analyze loaded patch to extract modified lines
        and statistics
        """
        assert self.patch is not None, "Missing patch"
        assert isinstance(self.patch, str), "Invalid patch type"

        # List all modified lines from current revision changes
        patch_stats = rs_parsepatch.get_lines(self.patch)
        assert len(patch_stats) > 0, "Empty patch"

        self.lines = {stat["filename"]: stat["added_lines"] for stat in patch_stats}

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
        if Path(settings.hgmo_cache) not in Path(cache_path).resolve().parents:
            logger.info("Element is not valid for caching, skipping", path=path)
            return

        if os.path.exists(cache_path):
            with open(cache_path) as f:
                return f.read()

        # Retrieve remote file
        url = urllib.parse.urljoin(
            "https://hg.mozilla.org",
            f"{self.head_repository}/raw-file/{self.head_changeset}/{path}",
        )
        logger.info("Downloading HGMO file", url=url)

        response = requests.get(url, headers=GetAppUserAgent())
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

    def add_improvement_patch(self, analyzer, content):
        """
        Save an improvement patch, and make it available
        as a Taskcluster artifact
        """
        assert isinstance(content, str)
        assert len(content) > 0
        self.improvement_patches.append(ImprovementPatch(analyzer, repr(self), content))

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
        if self.revision:
            return self.revision["fields"].get("title")
        if self.head_changeset is None:
            return None
        title = f"Changeset {self.head_changeset[:12]}"
        if self.head_repository:
            title += f" ({self.head_repository})"
        return title

    def as_dict(self):
        """
        Outputs a serializable representation of this revision
        """
        return {
            "diff_phid": self.diff_phid,
            "phid": self.phabricator_phid,
            "diff_id": self.diff_id,
            "id": self.phabricator_id,
            "url": self.url,
            "has_clang_files": self.has_clang_files,
            # Extra infos for frontend
            "title": self.title,
            "bugzilla_id": self.bugzilla_id,
            # Extra infos for backend
            "repository": self.head_repository,
            "target_repository": self.base_repository,
            "mercurial_revision": self.head_changeset,
            # New names that should be used instead of the old
            # repository, target_repository and mercurial_revision ones
            "head_repository": self.head_repository,
            "base_repository": self.base_repository,
            "head_changeset": self.head_changeset,
            "base_changeset": self.base_changeset,
        }
