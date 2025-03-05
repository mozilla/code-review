# Code review bot for developers

This documentation is targeted towards developers of the code review bot itself, or developers of analyzers who want to integrate it in our bot.

Here is the overall summary of available documentation:

- [System Architecture](architecture.md) (good starting point)
- [System Configuration](configuration.md)
- [How to debug the code review bot](debugging.md) and other tips for maintainers
- [CI/CD Pipeline](ci-cd/README.md) with Taskcluster
- [Phabricator](phabricator.md) integrations, lessons learned, tips & tricks
- Projects details:
  - [backend](projects/backend.md)
  - [bot](projects/bot.md)
  - [frontend](projects/bot.md)
- How to add a new analyzer:
  - [How to trigger your task on new diffs](trigger.md)
  - [How to publish issues on Phabricator](publication.md)
  - [Analyzer output format](analysis_format.md)
- [How to hook up a new repository](new_repository.md)

You can contact the code review bot's developers directly, see [README](../README.md) for contact info.
