# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

logger = structlog.get_logger(__name__)

A11Y_GROUP_SLUG = "accessibility-frontend-reviewers"

# Used to detect whether the bot has already handled this revision,
# by searching prior comments for this marker text.
COMMENT_MARKER = "You've tagged the accessibility team for review."

COMMENT_A11Y_REVIEW = """You've tagged the accessibility team for review.

If you've already spoken to a team member about your request, please request review from the specific team member you spoke to.

Otherwise, please do ALL of the following:
  * Post a comment describing the specific accessibility behaviour you're looking for feedback about
  * Attach screenshots showing behaviour before and after your patch (if this is a visual change)
  * Post a description of screen reader output/behaviour before and after your patch (if this change affects assistive technology users)

Once you have posted all of the above, please re-add the group. The group will not be removed again after you re-add it if the above conditions are met.
"""


def handle_a11y_review_group(api, revision):
    """
    Workflow for the #accessibility-frontend-reviewers group:

    1. If the group is not currently tagged on the revision, do nothing.
    2. If the group was added by an accessibility team member (i.e. a member of the
       accessibility-frontend-reviewers project in Phabricator), leave it alone.
    3. If this is the FIRST time a non-team-member has tagged the group (no prior bot comment):
       - Post the instructions comment.
       - Remove the group from reviewers.
    4. If the author re-added the group after the bot removed it, check whether they
       have followed the instructions by verifying at least one of:
       - A comment was posted by the revision author after the bot's removal.
       - An individual accessibility team member has been tagged as a reviewer.
       If either condition holds, leave the group in place.
       If neither holds, re-post the comment and remove the group.

    Prior bot handling is detected by searching the revision's transaction history
    for a comment authored by this bot that contains COMMENT_MARKER.
    """
    # Resolve the group's PHID and fetch the group's current member list.
    data = api.search_projects(slugs=[A11Y_GROUP_SLUG], attachments={"members": True})
    if not data or "phid" not in data[0]:
        logger.warning(
            "Unable to find PHID for accessibility reviewer group",
            slug=A11Y_GROUP_SLUG,
        )
        return

    group_phid = data[0]["phid"]
    team_member_phids = {
        m["phid"]
        for m in data[0].get("attachments", {}).get("members", {}).get("members", [])
    }

    # Verify the group is tagged for the current revision.
    revision_data = api.load_revision(
        rev_id=revision.phabricator_id, attachments={"reviewers": True}
    )
    group_reviewer_entry = next(
        (
            r
            for r in revision_data.get("attachments", {})
            .get("reviewers", {})
            .get("reviewers", [])
            if r["reviewerPHID"] == group_phid
        ),
        None,
    )

    if group_reviewer_entry is None:
        return

    # If an accessibility team member added the group, leave the group assigned and exit the workflow.
    actor_phid = group_reviewer_entry.get("actorPHID")
    if actor_phid and actor_phid in team_member_phids:
        logger.info(
            "Accessibility reviewer group added by team member, taking no action",
            revision_id=revision.phabricator_id,
            actor_phid=actor_phid,
        )
        return

    # Group is present and was added by a non-team-member. Search the revision's
    # transaction history for a prior bot comment containing COMMENT_MARKER.
    # If found, the bot has already handled this revision once (this is a re-add).
    bot_phid = api.user["phid"]
    all_reviewers = (
        revision_data.get("attachments", {}).get("reviewers", {}).get("reviewers", [])
    )
    transactions = api.request(
        "transaction.search", objectIdentifier=revision.phabricator_phid
    )
    transaction_data = transactions.get("data", [])

    bot_comment_timestamp = None
    for transaction in transaction_data:
        if transaction.get("authorPHID") != bot_phid:
            continue
        for comment in transaction.get("comments", []):
            if COMMENT_MARKER in comment.get("content", {}).get("raw", ""):
                bot_comment_timestamp = transaction["dateCreated"]
                break
        if bot_comment_timestamp is not None:
            break

    if bot_comment_timestamp is not None:
        # This is a re-add by a non-team-member (team member adds are handled above).
        # Verify the author has followed the instructions before allowing the group to stay.

        # Check 1: did the revision author post a comment after the bot's removal?
        author_phid = revision_data["fields"]["authorPHID"]
        has_followup_comment = any(
            any(c.get("content", {}).get("raw") for c in tx.get("comments", []))
            for tx in transaction_data
            if tx.get("authorPHID") == author_phid
            and tx.get("dateCreated", 0) > bot_comment_timestamp
        )

        # Check 2: has an individual accessibility team member been tagged?
        current_reviewer_phids = {r["reviewerPHID"] for r in all_reviewers}
        has_individual_team_reviewer = bool(current_reviewer_phids & team_member_phids)

        if has_followup_comment or has_individual_team_reviewer:
            logger.info(
                "Accessibility reviewer group legitimately re-added, taking no action",
                revision_id=revision.phabricator_id,
                has_followup_comment=has_followup_comment,
                has_individual_team_reviewer=has_individual_team_reviewer,
            )
            return

        # Premature re-add: re-post the comment so the author knows why the group
        # is being removed again, then remove it.
        logger.info(
            "Accessibility reviewer group re-added without required context, removing group again",
            revision_id=revision.phabricator_id,
        )
        api.comment(revision.phabricator_id, COMMENT_A11Y_REVIEW)
        api.edit_revision(
            revision.phabricator_id,
            [{"type": "reviewers.remove", "value": [group_phid]}],
        )
        return

    # First time the group has been tagged by a non-team-member: post the
    # instructions comment and remove the group.
    logger.info(
        "Accessibility reviewer group tagged for first time, posting comment and removing group",
        revision_id=revision.phabricator_id,
    )

    api.comment(revision.phabricator_id, COMMENT_A11Y_REVIEW)

    api.edit_revision(
        revision.phabricator_id,
        [{"type": "reviewers.remove", "value": [group_phid]}],
    )
