# How to trigger your task on new diffs

## Requirements

1. Your repository must use [Mozilla Phabricator's instance](https://phabricator.services.mozilla.com/)
2. Your repository must use [Taskcluster as CI](https://docs.taskcluster.net) (at least one task must start on each push).
3. You are adding a Taskcluster task that runs on each push, analyzes the modified source code and lists potential issues.

## Step for mozilla-central

:warning: This step is specific to mozilla-central and its taskgraph. Other repositories have different decision tasks and mechanisms.

Once your task is setup in the repository taskgraph, usually in [taskcluster/ci/source-test](https://github.com/mozilla/release-services/issues/2254), you'll need to add an attribute to the task definition so the code-review bot will automatically start your task on new diffs.

It's simple to add:

```yaml
attributes:
  code-review: true
```

Here is an example for [clang tasks](https://hg.mozilla.org/mozilla-central/file/tip/taskcluster/ci/source-test/clang.yml#l12)

Ask [bastien](https://phabricator.services.mozilla.com/p/bastien/) for review on that step, especially if you add a task in a different namespace than `source-test`

## Step for NSS

[NSS](https://phabricator.services.mozilla.com/source/nss/) is already integrated in the code-review bot workflow, using its own decision task (no taskgraph here).

To add a new analyzer, you'll need to add a task in `automation/taskcluster/graph/src/extend.js`, with the tag `code-review`. You can lookup the `coverity` for a sample implementation.

## Step for other repositories

Please reach out to our team, look in [README](../README.md) for contact information.
