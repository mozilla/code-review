# -*- coding: utf-8 -*-

import pytest
from libmozevent.bus import MessageBus
from libmozevent.phabricator import PhabricatorBuild

from code_review_events.workflow import CodeReview


class MockURL:
    def __init__(self, **kwargs):
        self.query = kwargs


class MockRequest:
    def __init__(self, **kwargs):
        self.rel_url = MockURL(**kwargs)


@pytest.mark.asyncio
async def test_risk_analysis_should_trigger(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    with PhabricatorMock as phab:
        client = CodeReview(
            risk_analysis_reviewers=["ehsan", "heycam"],
            url="http://phabricator.test/api/",
            api_key="fakekey",
            community_config={"client_id": "xxx", "access_token": "yyy"},
        )
        client.register(bus)

        phab.update_state(build)
        phab.load_reviewers(build)

    assert client.should_run_risk_analysis(build)


@pytest.mark.asyncio
async def test_risk_analysis_shouldnt_trigger(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    with PhabricatorMock as phab:
        client = CodeReview(
            risk_analysis_reviewers=["ehsan"],
            url="http://phabricator.test/api/",
            api_key="fakekey",
            community_config={"client_id": "xxx", "access_token": "yyy"},
        )
        client.register(bus)

        phab.update_state(build)
        phab.load_reviewers(build)

    assert not client.should_run_risk_analysis(build)


@pytest.mark.asyncio
async def test_blacklist(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="123456",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="98765",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    with PhabricatorMock as phab:
        client = CodeReview(
            user_blacklist=["baduser123"],
            url="http://phabricator.test/api/",
            api_key="fakekey",
            community_config={"client_id": "xxx", "access_token": "yyy"},
        )
        client.register(bus)

        assert client.user_blacklist == [
            {
                "attachments": {},
                "fields": {
                    "dateCreated": 1574083856,
                    "dateModified": 1574083857,
                    "policy": {"edit": "admin", "view": "public"},
                    "realName": "Bad boy de Mars.",
                    "roles": ["bot", "verified", "approved", "activated"],
                    "username": "baduser123",
                },
                "id": 1460,
                "phid": "PHID-USER-baduser123",
                "type": "USER",
            }
        ]

        phab.update_state(build)

        assert build.revision["fields"]["authorPHID"] == "PHID-USER-baduser123"

    assert client.is_blacklisted(build.revision)
