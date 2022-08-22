# -*- coding: utf-8 -*-

import pytest
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import ConduitError
from libmozdata.phabricator import UnitResultState
from libmozevent.bus import MessageBus
from libmozevent.phabricator import PhabricatorBuild
from structlog.testing import capture_logs

from code_review_events import QUEUE_BUGBUG
from code_review_events import QUEUE_MERCURIAL
from code_review_events.workflow import LANDO_FAILURE_HG_MESSAGE
from code_review_events.workflow import LANDO_FAILURE_MESSAGE
from code_review_events.workflow import LANDO_WARNING_MESSAGE
from code_review_events.workflow import CodeReview

MOCK_LANDO_API_URL = "http://api.lando.test"
MOCK_LANDO_TOKEN = "Some Test Token"


class MockLandoWarnings(object):
    """
    LandoWarnings Mock class
    """

    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key
        self.revision_id = None

    def add_warning(self, warning, revision_id, diff_id):
        self.revision_id = revision_id
        self.diff_id = diff_id
        self.warning = warning

    def del_all_warnings(self, revision_id, diff_id):
        self.revision_id = revision_id
        self.diff_id = diff_id


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
            lando_url=None,
            lando_publish_generic_failure=False,
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
            lando_url=None,
            lando_publish_generic_failure=False,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
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
async def test_publish_results_success_mode_missing_base_rev(
    PhabricatorMock, mock_taskcluster
):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )
    build.missing_base_revision = True

    with PhabricatorMock as phab:
        client = CodeReview(
            lando_url=None,
            lando_publish_generic_failure=False,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
        )
        client.register(bus)

        phab.update_state(build)

        with capture_logs() as cap_logs:
            await client.publish_results(
                (
                    "success",
                    build,
                    {"treeherder_url": "https://treeherder.org/", "revision": "123"},
                )
            )

            assert cap_logs == [
                {
                    "event": "Publishing a Phabricator build update",
                    "log_level": "debug",
                    "mode": "success",
                    "build": build,
                },
                {
                    "event": "Missing base revision on PhabricatorBuild, adding a warning to Unit Tests section on Phabricator",
                    "log_level": "debug",
                },
            ]


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
            lando_url=None,
            lando_publish_generic_failure=False,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
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
            lando_url=None,
            lando_publish_generic_failure=False,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
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


@pytest.mark.asyncio
async def test_publish_results_lando_success(PhabricatorMock, mock_taskcluster):
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
            lando_url=None,
            lando_publish_generic_failure=True,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
        )
        client.register(bus)

        client.publish_lando = True
        client.lando_warnings = MockLandoWarnings(MOCK_LANDO_API_URL, MOCK_LANDO_TOKEN)

        client.bus.add_queue(QUEUE_BUGBUG)
        client.bus.add_queue(QUEUE_MERCURIAL)

        phab.update_state(build)

        await client.process_build(build)

        assert client.lando_warnings.revision_id == build.revision["id"]
        assert client.lando_warnings.diff_id == build.diff_id
        assert client.lando_warnings.warning == LANDO_WARNING_MESSAGE

        await client.publish_results(
            (
                "success",
                build,
                {"treeherder_url": "https://treeherder.org/", "revision": "123"},
            )
        )

        # Verify lando warning when mercurial failure occurs
        with pytest.raises(ConduitError):
            await client.publish_results(
                (
                    "fail:mercurial",
                    build,
                    {
                        "treeherder_url": "https://treeherder.org/",
                        "revision": "123",
                        "message": "failure message",
                    },
                )
            )
        assert client.lando_warnings.warning == LANDO_FAILURE_HG_MESSAGE


@pytest.mark.asyncio
async def test_publish_results_fail(PhabricatorMock, mock_taskcluster):
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
            lando_url=None,
            lando_publish_generic_failure=True,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
        )
        client.register(bus)

        client.publish_lando = True
        client.lando_warnings = MockLandoWarnings(MOCK_LANDO_API_URL, MOCK_LANDO_TOKEN)

        client.bus.add_queue(QUEUE_BUGBUG)
        client.bus.add_queue(QUEUE_MERCURIAL)

        phab.update_state(build)

        await client.process_build(build)

        # Verify lando warning when mercurial failure occurs
        with pytest.raises(ConduitError):
            await client.publish_results(
                (
                    "fail:mercurial",
                    build,
                    {
                        "treeherder_url": "https://treeherder.org/",
                        "revision": "123",
                        "message": "failure message",
                    },
                )
            )
        assert client.lando_warnings.warning == LANDO_FAILURE_HG_MESSAGE


@pytest.mark.asyncio
async def test_publish_results_lando_general_fail(PhabricatorMock, mock_taskcluster):
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
            lando_url=None,
            lando_publish_generic_failure=True,
            publish=True,
            url="http://phabricator.test/api/",
            api_key="fakekey",
        )
        client.register(bus)

        client.publish_lando = True
        client.lando_warnings = MockLandoWarnings(MOCK_LANDO_API_URL, MOCK_LANDO_TOKEN)

        client.bus.add_queue(QUEUE_BUGBUG)
        client.bus.add_queue(QUEUE_MERCURIAL)

        phab.update_state(build)

        await client.process_build(build)

        # Verify lando warning when general failure occurs
        with pytest.raises(ConduitError):
            await client.publish_results(
                (
                    "fail:general",
                    build,
                    {
                        "treeherder_url": "https://treeherder.org/",
                        "revision": "123",
                        "message": "failure message",
                    },
                )
            )
        assert client.lando_warnings.warning == LANDO_FAILURE_MESSAGE
