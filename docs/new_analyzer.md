# How to add a new analyzer on the code review bot

## Requirements

1. Your repository must use [Mozilla Phabricator's instance](https://phabricator.services.mozilla.com/)
2. Your repository must use [Taskcluster as CI](https://docs.taskcluster.net) (at least one task must start on each push).
3. You are adding a Taskcluster task that runs on each push, analyses the modified source code and lists potential issues.

## Build analysis output

TODO: Default [analysis format](bot/analysis_format.md).


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
