# How to add a new analyzer on the code review bot

## Requirements

1. Your repository must use [Mozilla Phabricator's instance](https://phabricator.services.mozilla.com/)
2. Your repository must use [Taskcluster as CI](https://docs.taskcluster.net) (at least one task must start on each push).
3. You are adding a Taskcluster task that runs on each push, analyses the modified source code and lists potential issues.

## Build analysis output

TODO: Default [analysis format](analysis_format.md).

TODO: describe Taskcluster public artifacts


## Add code-review

:warning: This step is specific to mozilla-central and its taskgraph. Other repositories have different decision tasks & mechanisms.

Once your task is setup in the repository taskgraph, usually in [taskcluster/ci/source-test](https://github.com/mozilla/release-services/issues/2254), you'll need to add an attribute to the task definition so the code-review bot will automatically start your task on new diffs.

It's simple to add:

```yaml
attributes:
  code-review: true
```

Here is an example for [clang tasks](https://hg.mozilla.org/mozilla-central/file/tip/taskcluster/ci/source-test/clang.yml#l12)

## Publish results on Phabricator

Once your task is triggered with the `code-review` attribute, its analysis artifact should be retrieved automatically by the bot if you use the default format.

If you produce a different format, this will need a specific implementation on the bot (:mag: doc needed here)

TODO: describe filtering

## Troubleshooting

1. Check that your task is triggered by the decision task on new diffs
2. Check that your task is present in the task group published by the code review bot as `Treeherder jobs`
3. Check that your task produces the expected analysis artifact
4. Check that the `code-review-issues` is present in that task group (for mozilla-central tasks)
5. Check that your test diff is available on [our dashboard](https://static-analysis.moz.tools/) by searching its revision ID or title (it can take several seconds to load all the tasks available)
6. Reach out to developers on Slack #code-review-bot
