# How to trigger your task on new diffs

## Step for mozilla-central

:warning: This step is specific to mozilla-central and its taskgraph. Other repositories have different decision tasks and mechanisms.

Once your task is setup in the repository taskgraph, usually in [taskcluster/ci/source-test](https://github.com/mozilla/release-services/issues/2254), you'll need to add an attribute to the task definition so the code-review bot will automatically start your task on new diffs.

It's simple to add:

```yaml
attributes:
  code-review: true
```

Here is an example for [clang tasks](https://hg.mozilla.org/mozilla-central/file/177ac92fb734b80f07c04710ec70f0b89a073351/taskcluster/ci/source-test/clang.yml#l12)

Ask the [linter-reviewers group](https://phabricator.services.mozilla.com/project/view/119/) for review on that step, especially if you add a task in a different namespace than `source-test`

## Step for NSS

[NSS](https://phabricator.services.mozilla.com/source/nss/) is already integrated in the code-review bot workflow, using its own decision task (no taskgraph here).

To add a new analyzer, you'll need to add a task in `automation/taskcluster/graph/src/extend.js`, with the tag `code-review`. You can lookup the `coverity` for a sample implementation.
