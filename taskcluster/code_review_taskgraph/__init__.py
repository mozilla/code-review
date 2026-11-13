import os
from importlib import import_module

COMMUNITY_TC_ROOT_URL = "https://community-tc.services.mozilla.com"


def register(graph_config):
    if _running_on_community_tc():
        _use_community_tc_pools(graph_config)
    _import_modules(["parameters"])


def _running_on_community_tc():
    return (
        os.environ.get("TASKCLUSTER_ROOT_URL", "").rstrip("/") == COMMUNITY_TC_ROOT_URL
    )


def _use_community_tc_pools(graph_config):
    for alias in graph_config["workers"]["aliases"].values():
        alias["provisioner"] = "proj-relman"
        alias["worker-type"] = "{trust-domain}-{level}-" + alias["worker-type"]


def _import_modules(modules):
    for module in modules:
        import_module(f".{module}", package=__name__)
