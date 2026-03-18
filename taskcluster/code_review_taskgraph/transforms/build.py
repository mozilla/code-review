import re

from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()

INDEX_NAME_UNSUPPORTED_CHARACTERS = re.compile(r"[^a-zA-Z0-9_!~*'()%.-]")


@transforms.add
def add_index_routes(config, tasks):
    for task in tasks:
        params = config.params
        head_rev = params["head_rev"]
        branch = INDEX_NAME_UNSUPPORTED_CHARACTERS.sub("_", params["short_head_ref"])

        if params["tasks_for"] == "github-pull-request":
            index_prefix = "code-review-pr"
        else:
            index_prefix = "code-review"

        trust_domain = config.graph_config["trust-domain"]
        task.setdefault("routes", []).extend(
            [
                f"index.{trust_domain}.v2.{index_prefix}.{task['name']}.revision.{head_rev}",
                f"index.{trust_domain}.v2.{index_prefix}.{task['name']}.branch.{branch}",
            ]
        )

        yield task
