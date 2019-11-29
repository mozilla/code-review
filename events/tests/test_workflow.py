# -*- coding: utf-8 -*-
import pytest
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import UnitResultState
from libmozevent import taskcluster_config
from libmozevent.bus import MessageBus
from libmozevent.phabricator import PhabricatorBuild

from code_review_events import QUEUE_BUGBUG_TRY_PUSH
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events.bugbug_utils import BugbugUtils
from code_review_events.workflow import CodeReview


class MockURL:
    def __init__(self, **kwargs):
        self.query = kwargs


class MockRequest:
    def __init__(self, **kwargs):
        self.rel_url = MockURL(**kwargs)


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
        )
        client.register(bus)

        assert client.user_blacklist == {"PHID-USER-baduser123": "baduser123"}

        phab.update_state(build)

        assert build.revision["fields"]["authorPHID"] == "PHID-USER-baduser123"

    assert client.is_blacklisted(build.revision)


@pytest.mark.asyncio
async def test_dispatch_mercurial_applied(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    taskcluster_config.secrets = {
        "test_selection_enabled": True,
        "test_selection_share": 0.1,
        "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
    }

    with PhabricatorMock as phab:
        client = CodeReview(
            publish=True, url="http://phabricator.test/api/", api_key="fakekey"
        )
        client.register(bus)

        bugbug_utils = BugbugUtils()
        bugbug_utils.register(bus)

        phab.update_state(build)

        assert bus.queues[QUEUE_PHABRICATOR_RESULTS].empty()
        assert bus.queues[QUEUE_BUGBUG_TRY_PUSH].empty()

        await client.dispatch_mercurial_applied(
            (
                "success",
                build,
                {"treeherder_url": "https://treeherder.org/", "revision": "123"},
            )
        )

        mode, build_, extras = await bus.receive(QUEUE_PHABRICATOR_RESULTS)
        assert mode == "success"
        assert build_ == build
        assert extras == {
            "treeherder_url": "https://treeherder.org/",
            "revision": "123",
        }

        mode, build_, extras = await bus.receive(QUEUE_BUGBUG_TRY_PUSH)
        assert mode == "success"
        assert build_ == build
        assert extras == {
            "treeherder_url": "https://treeherder.org/",
            "revision": "123",
        }


@pytest.mark.asyncio
async def test_publish_results_success_mode(PhabricatorMock, mock_taskcluster):
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
            publish=True, url="http://phabricator.test/api/", api_key="fakekey"
        )
        client.register(bus)

        phab.update_state(build)

        client.publish_results(
            (
                "success",
                build,
                {"treeherder_url": "https://treeherder.org/", "revision": "123"},
            )
        )


@pytest.mark.asyncio
async def test_publish_results_test_result_mode(PhabricatorMock, mock_taskcluster):
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
            publish=True, url="http://phabricator.test/api/", api_key="fakekey"
        )
        client.register(bus)

        phab.update_state(build)

        orig = client.api.update_build_target

        def new(build_target_phid, state, unit=[], lint=[]):
            assert build_target_phid == "PHID-HMBT-icusvlfibcebizyd33op"
            assert state == BuildState.Work
            assert len(unit) == 1
            assert unit[0]["namespace"] == "code-review"
            assert unit[0]["name"] == "test-linux64-shippable/opt-awsy-tp6-e10s"
            assert unit[0]["result"] == "pass"
            orig(build_target_phid, state, unit, lint)

        client.api.update_build_target = new

        client.publish_results(
            (
                "test_result",
                build,
                {
                    "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
                    "result": UnitResultState.Pass,
                },
            )
        )

        def new(build_target_phid, state, unit=[], lint=[]):
            assert build_target_phid == "PHID-HMBT-icusvlfibcebizyd33op"
            assert state == BuildState.Work
            assert len(unit) == 1
            assert unit[0]["namespace"] == "code-review"
            assert unit[0]["name"] == "test-windows10-64/opt-mochitest-1"
            assert unit[0]["result"] == "fail"
            orig(build_target_phid, state, unit, lint)

        client.api.update_build_target = new

        client.publish_results(
            (
                "test_result",
                build,
                {
                    "name": "test-windows10-64/opt-mochitest-1",
                    "result": UnitResultState.Fail,
                },
            )
        )
