# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.revision import Revision


class GithubRevision(Revision):
    """
    A revision from a github pull-request
    """

    def __init__(self, repo_url, branch, pull_number, pull_head_sha):
        self.repo_url = repo_url
        self.branch = branch
        self.pull_number = pull_number
        self.pull_head_sha = pull_head_sha

    def __str__(self):
        return f"Github pull request {self.repo_url} #{self.pull_number} ({self.pull_head_sha[:8]})"
