# Code Review Frontend

The frontend is a Single Page Application, built with [Vue.JS](https://vuejs.org), using [vuex](https://vuex.vuejs.org/) as a store to get reactive programming share across components.

It's really a pretty simple application, not much complexity:
- few views, and few components
- uses [axios](https://github.com/axios/axios) to retrieve data from the backend
- no authentication, everything is public
- uses [chartist](https://gionkunz.github.io/chartist-js/) to build the stats graph
- uses [vue-router](https://router.vuejs.org/) to handle routing

The application is built with [neutrino](https://neutrinojs.org/) (a Mozilla project) using its defaults for Vue.js application.

On every Github push (pull request or branch), the frontend is built, and even usable from the Taskcluster artifacts (it uses the testing environment as its default source).

The application is then deployed with [task-boot](https://github.com/mozilla/task-boot/) on an Amazon S3 bucket, exposed through a Cloudfront configuration (this is managed by the Cloudops team at Mozilla).

Finally the application is currently available as:
- https://code-review.moz.tools/ on production (uses production backend)
- https://code-review.testing.moz.tools/ on testing (uses testing backend)
