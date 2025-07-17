# How to hook up a new repository

## Requirements

1. Your repository must use [Mozilla Phabricator's instance](https://phabricator.services.mozilla.com/)
2. Your repository must use [Taskcluster as CI](https://community-tc.services.mozilla.com/docs) (at least one task must start on each push).
3. You are adding a Taskcluster task that runs on each push, analyzes the modified source code and lists potential issues.

## Contact us

As each new repository has different needs and constraints, please reach out to our team. Look in [README](../README.md) for contact information.

## Onboarding a new repository

⚠️ This section is for code-review bot administrators who wish to add a new repository into the system.

There are 2 places where configuration must be updated: Runtime configuration in Taskcluster, and the backend database.

### Runtime configuration in Taskcluster

You'll need to edit either the [testing](https://firefox-ci-tc.services.mozilla.com/secrets/project%2Frelman%2Fcode-review%2Fruntime-testing) or [production](https://firefox-ci-tc.services.mozilla.com/secrets/project%2Frelman%2Fcode-review%2Fruntime-production) secret that holds the runtime configuration for the bot.

The section to edit in the YAML content is `common.repositories`, which is a list of known repositories.

Each repository has the following structure:

```yaml
repositories:
  - checkout: robust
    try_url: ssh://hg.mozilla.org/try
    name: mozilla-central
    ssh_user: reviewbot
    url: https://hg.mozilla.org/mozilla-unified
    decision_env_revision: GECKO_HEAD_REV
    decision_env_repository: GECKO_HEAD_REPOSITORY
    decision_env_prefix: GECKO
```

The configuration [is explained in this documentation](./configuration.md) in details.

### Backend database

TODO
