# Github

Starting from 2026, the project was expannded to support revisions from sources other than Phabricator, particularly Github [pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests).

The code review bot automatically publishes a review containing the different comments, interacting with the Github API through the [App feature](https://docs.github.com/en/apps/using-github-apps/about-using-github-apps). It uses the [PyGithub](https://pypi.org/project/PyGithub/) external library to handle low level authentication steps.

## App setup

First, a Github App must be created and installed to your user or organisation. You can follow Github's [documentation](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/about-creating-github-apps#building-a-github-app) for this process.

Once the app is installed, you can manage it from the [installation settings in github](https://github.com/settings/installations). The App must have access to the repositories to which it should be allowed to publish comments.
It should be granted a **read** and **write** scope access to pull requests to be able to publish reviews. This can be configured through the **App settings** section of your installation.
On this page, you should be able to find the App **installation ID** required to configure the bot.

## Authentication

Once an App is installed and has the valid access scopes, you can generate a new secret key from the [App settings](https://github.com/settings/apps). In the private key section, click the **Generate a private key** button and save the generated `.pem` file.
On this page, you should be able to find the App **Client ID** required to configure the bot.

The code review bot YAML configuration should then be updated with the corresponding information:

```yaml
bot:
  REPORTERS:
    - reporter: github
      app_client_id: xxxxxxxxxxxxxxxxxxxx
      app_pem_file: /path/to/key.pem
      app_installation_id: 123456789
```
