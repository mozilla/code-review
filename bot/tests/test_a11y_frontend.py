# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import MagicMock

import pytest

from code_review_bot.tasks.a11y_frontend import (
    A11Y_GROUP_SLUG,
    COMMENT_A11Y_REVIEW,
    COMMENT_MARKER,
    handle_a11y_review_group,
)

GROUP_PHID = "PHID-PROJ-A11yReviewers"
TEAM_MEMBER_PHID = "PHID-USER-TeamMember"
NON_MEMBER_PHID = "PHID-USER-NonMember"
BOT_PHID = "PHID-USER-Bot"
REVISION_ID = 51
REVISION_PHID = "PHID-DREV-test"


@pytest.fixture
def api():
    mock = MagicMock()
    mock.user = {"phid": BOT_PHID}
    return mock


@pytest.fixture
def revision():
    mock = MagicMock()
    mock.phabricator_id = REVISION_ID
    mock.phabricator_phid = REVISION_PHID
    return mock


def _group_project(members=None):
    """Return a mock search_projects result for the a11y group."""
    return [
        {
            "phid": GROUP_PHID,
            "slug": A11Y_GROUP_SLUG,
            "attachments": {
                "members": {"members": [{"phid": p} for p in (members or [])]}
            },
        }
    ]


def _revision_with_reviewer(reviewer_phid, actor_phid, extra_reviewers=None):
    """Return a mock load_revision result with the given reviewer."""
    reviewers = [{"reviewerPHID": reviewer_phid, "actorPHID": actor_phid}]
    for phid in extra_reviewers or []:
        reviewers.append({"reviewerPHID": phid, "actorPHID": phid})
    return {
        "fields": {"authorPHID": NON_MEMBER_PHID},
        "attachments": {"reviewers": {"reviewers": reviewers}},
    }


def _revision_without_reviewer():
    """Return a mock load_revision result with no reviewers."""
    return {
        "fields": {"authorPHID": NON_MEMBER_PHID},
        "attachments": {"reviewers": {"reviewers": []}},
    }


def _transactions(bot_comment_ts=None, author_comment_ts=None):
    """Build a minimal transaction.search result."""
    data = []
    if bot_comment_ts is not None:
        data.append(
            {
                "authorPHID": BOT_PHID,
                "dateCreated": bot_comment_ts,
                "comments": [{"content": {"raw": COMMENT_MARKER + " extra text"}}],
            }
        )
    if author_comment_ts is not None:
        data.append(
            {
                "authorPHID": NON_MEMBER_PHID,
                "dateCreated": author_comment_ts,
                "comments": [
                    {"content": {"raw": "Here is my accessibility description."}}
                ],
            }
        )
    return {"data": data}


def test_first_time_tagging(api, revision):
    """First-time tag by a non-team-member: post comment and remove group."""
    api.search_projects.return_value = _group_project(members=[])
    api.load_revision.return_value = _revision_with_reviewer(
        GROUP_PHID, NON_MEMBER_PHID
    )
    api.request.return_value = _transactions()

    handle_a11y_review_group(api, revision)

    api.comment.assert_called_once_with(REVISION_ID, COMMENT_A11Y_REVIEW)
    api.edit_revision.assert_called_once_with(
        REVISION_ID, [{"type": "reviewers.remove", "value": [GROUP_PHID]}]
    )


def test_team_member_tagging(api, revision):
    """Group added by an accessibility team member: leave it in place."""
    api.search_projects.return_value = _group_project(members=[TEAM_MEMBER_PHID])
    api.load_revision.return_value = _revision_with_reviewer(
        GROUP_PHID, TEAM_MEMBER_PHID
    )

    handle_a11y_review_group(api, revision)

    api.comment.assert_not_called()
    api.edit_revision.assert_not_called()


def test_legitimate_readd_via_comment(api, revision):
    """Re-add after the author posted a followup comment: group stays."""
    api.search_projects.return_value = _group_project(members=[])
    api.load_revision.return_value = _revision_with_reviewer(
        GROUP_PHID, NON_MEMBER_PHID
    )
    # Bot commented at t=100, author commented at t=200 (after removal)
    api.request.return_value = _transactions(bot_comment_ts=100, author_comment_ts=200)

    handle_a11y_review_group(api, revision)

    api.comment.assert_not_called()
    api.edit_revision.assert_not_called()


def test_legitimate_readd_via_individual_team_reviewer(api, revision):
    """Re-add after the author tagged an individual team member: group stays."""
    api.search_projects.return_value = _group_project(members=[TEAM_MEMBER_PHID])
    # Group is tagged (by non-member), AND individual team member is also a reviewer
    api.load_revision.return_value = _revision_with_reviewer(
        GROUP_PHID, NON_MEMBER_PHID, extra_reviewers=[TEAM_MEMBER_PHID]
    )
    # Bot previously commented, but no author followup comment
    api.request.return_value = _transactions(bot_comment_ts=100)

    handle_a11y_review_group(api, revision)

    api.comment.assert_not_called()
    api.edit_revision.assert_not_called()


def test_premature_readd(api, revision):
    """Re-add without followup comment or individual team member: remove group again."""
    api.search_projects.return_value = _group_project(members=[])
    api.load_revision.return_value = _revision_with_reviewer(
        GROUP_PHID, NON_MEMBER_PHID
    )
    # Bot previously commented, no author followup, no individual team reviewer
    api.request.return_value = _transactions(bot_comment_ts=100)

    handle_a11y_review_group(api, revision)

    api.comment.assert_called_once_with(REVISION_ID, COMMENT_A11Y_REVIEW)
    api.edit_revision.assert_called_once_with(
        REVISION_ID, [{"type": "reviewers.remove", "value": [GROUP_PHID]}]
    )


def test_group_not_present(api, revision):
    """Group not on the revision: do nothing."""
    api.search_projects.return_value = _group_project(members=[])
    api.load_revision.return_value = _revision_without_reviewer()

    handle_a11y_review_group(api, revision)

    api.comment.assert_not_called()
    api.edit_revision.assert_not_called()
    api.request.assert_not_called()


def test_group_phid_not_found(api, revision):
    """Project search returns nothing: log warning and do nothing."""
    api.search_projects.return_value = []

    handle_a11y_review_group(api, revision)

    api.load_revision.assert_not_called()
    api.comment.assert_not_called()
    api.edit_revision.assert_not_called()
