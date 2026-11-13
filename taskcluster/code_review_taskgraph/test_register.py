import pytest

from code_review_taskgraph import register

FIREFOX_CI_ROOT_URL = "https://firefox-ci-tc.services.mozilla.com"
COMMUNITY_TC_ROOT_URL = "https://community-tc.services.mozilla.com"


def make_graph_config():
    return {
        "trust-domain": "code-analysis",
        "workers": {
            "aliases": {
                "b-linux": {
                    "provisioner": "{trust-domain}-{level}",
                    "worker-type": "linux-docker",
                },
                "images": {
                    "provisioner": "{trust-domain}-{level}",
                    "worker-type": "linux-gcp",
                },
            }
        },
    }


@pytest.mark.parametrize("root_url", [FIREFOX_CI_ROOT_URL, None])
def test_register_keeps_aliases_outside_community_tc(monkeypatch, root_url):
    if root_url is None:
        monkeypatch.delenv("TASKCLUSTER_ROOT_URL", raising=False)
    else:
        monkeypatch.setenv("TASKCLUSTER_ROOT_URL", root_url)
    graph_config = make_graph_config()

    register(graph_config)

    assert graph_config == make_graph_config()


@pytest.mark.parametrize(
    "alias, worker_type",
    [("b-linux", "linux-docker"), ("images", "linux-gcp")],
)
def test_register_moves_aliases_to_community_tc_pools(monkeypatch, alias, worker_type):
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", COMMUNITY_TC_ROOT_URL)
    graph_config = make_graph_config()

    register(graph_config)

    assert graph_config["workers"]["aliases"][alias] == {
        "provisioner": "proj-relman",
        "worker-type": "{trust-domain}-{level}-" + worker_type,
    }
