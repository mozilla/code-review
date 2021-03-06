# -*- coding: utf-8 -*-
import pytest
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import UnitResultState
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

        await client.publish_results(
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
            assert unit[0] == {
                "namespace": "code-review",
                "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
                "result": "pass",
            }
            orig(build_target_phid, state, unit, lint)

        client.api.update_build_target = new

        await client.publish_results(
            (
                "test_result",
                build,
                {
                    "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
                    "result": UnitResultState.Pass,
                    "details": None,
                },
            )
        )

        def new(build_target_phid, state, unit=[], lint=[]):
            assert build_target_phid == "PHID-HMBT-icusvlfibcebizyd33op"
            assert state == BuildState.Work
            assert len(unit) == 1
            assert unit[0] == {
                "namespace": "code-review",
                "name": "test-windows10-64/opt-mochitest-1",
                "result": "fail",
                "details": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=028980a035fb3e214f7645675a01a52234aad0fe&selectedJob=277665740",
            }
            orig(build_target_phid, state, unit, lint)

        client.api.update_build_target = new

        await client.publish_results(
            (
                "test_result",
                build,
                {
                    "name": "test-windows10-64/opt-mochitest-1",
                    "result": UnitResultState.Fail,
                    "details": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=028980a035fb3e214f7645675a01a52234aad0fe&selectedJob=277665740",
                },
            )
        )


def test_repositories(PhabricatorMock, mock_taskcluster, tmpdir):
    configuration = [
        {
            "checkout": "robust",
            "try_url": "ssh://hg.mozilla.org/try",
            "try_mode": "json",
            "name": "mozilla-central",
            "ssh_user": "someone@mozilla.com",
            "url": "https://hg.mozilla.org/mozilla-central/",
        },
        {
            "checkout": "batch",
            "try_url": "https://hg.mozilla.org/projects/nss-try",
            "try_mode": "json",
            "name": "nss",
            "ssh_user": "someone@mozilla.com",
            "ssh_key": "custom NSS secret key",
            "url": "https://hg.mozilla.org/projects/nss",
        },
    ]
    with PhabricatorMock:
        client = CodeReview(
            publish=True, url="http://phabricator.test/api/", api_key="fakekey"
        )
        repositories = client.get_repositories(
            configuration, tmpdir, default_ssh_key="DEFAULT FAKE KEY"
        )

    assert len(repositories) == 2

    # Check mc has the default key
    assert "PHID-REPO-mc" in repositories
    mc = repositories["PHID-REPO-mc"]
    assert mc.name == "mozilla-central"
    assert open(mc.ssh_key_path).read() == "DEFAULT FAKE KEY"

    # Check nss has its own key
    assert "PHID-REPO-mc" in repositories
    nss = repositories["PHID-REPO-nss"]
    assert nss.name == "nss"
    assert open(nss.ssh_key_path).read() == "custom NSS secret key"
