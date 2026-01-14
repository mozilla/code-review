# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import random
from datetime import timedelta

import rs_parsepatch
import structlog
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue, stats, taskcluster
from code_review_bot.config import (
    settings,
)
from code_review_bot.revisions.github import GithubRevision
from code_review_bot.revisions.phabricator import PhabricatorRevision
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
    A generic revision to override using provider specific details
    """

    def __init__(
        self,
    ):
        # backend's returned URL to list or create issues linked to the revision in bulk (diff is optional)
        self.issues_url = None

        # Patches built later on
        self.improvement_patches = []

        # Patch analysis
        self.files = []
        self.lines = {}

    @property
    def namespaces(self):
        raise NotImplementedError

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
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError

    @staticmethod
    def from_try_task(try_task: dict, decision_task: dict, phabricator: PhabricatorAPI):
        """
        Load identifiers from Phabricator, using the remote task description
        """

        # Load build target phid from the task env
        code_review = try_task["extra"]["code-review"]

        if "github" in code_review:
            return GithubRevision(**code_review["github"])
        else:
            return PhabricatorRevision.from_try_task(
                code_review, decision_task, phabricator
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
        raise NotImplementedError

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

    @property
    def is_blacklisted(self):
        raise NotImplementedError

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
        raise NotImplementedError

    @property
    def title(self):
        raise NotImplementedError

    def as_dict(self):
        """
        Outputs a serializable representation of this revision
        """
        raise NotImplementedError
