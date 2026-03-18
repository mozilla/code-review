from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()

UNTRUSTED_TASKS_FOR = "github-pull-request-untrusted"


@transforms.add
def disable_caches_for_untrusted(config, tasks):
    for task in tasks:
        if config.params["tasks_for"] == UNTRUSTED_TASKS_FOR and "run" in task:
            task["run"]["use-caches"] = False
        yield task
