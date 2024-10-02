import Vue from "vue";
import Vuex from "vuex";
import axios from "axios";
Vue.use(Vuex);
import { createStore } from "vuex";

const TASKCLUSTER_DIFF_INDEX =
  "https://index.taskcluster.net/v1/task/project.relman.production.code-review.phabricator.diff.";

const store = createStore({
  state: {
    backend_url: BACKEND_URL,
    tasks: [],
    diffs: {},
    stats: null,
    total_stats: 0, // Used to track download progress
    states: null,
    repositories: null,
    diff: null,
    issues: {},
    check_issues: {},
    history: null,
    revision: null,
  },
  mutations: {
    reset(state) {
      state.tasks = [];
      state.diffs = {};
      state.diff = null;
    },

    reset_stats(state) {
      state.stats = [];
      state.total_stats = 0;
    },

    use_tasks(state, tasks) {
      state.tasks = state.tasks.concat(tasks.tasks);
    },

    use_diffs(state, diffs) {
      // Simply store diffs & their current pagination
      state.diffs = diffs;
    },

    use_repositories(state, repositories) {
      // Simply store repositories directly
      state.repositories = repositories;
    },

    use_revision(state, payload) {
      state.revision = Object.assign(payload.revision, {
        diffs: payload.diffs,
      });
    },

    // Store a new diff to display
    use_diff(state, diff) {
      state.diff = diff;
      if (state.diff !== null) {
        state.diff.issues = [];
      }
    },

    // Add issues to a diff
    add_issues(state, payload) {
      const update = {};
      const issues = state.issues[payload.diffId] || [];
      update[payload.diffId] = issues.concat(payload.issues);
      state.issues = Object.assign({}, state.issues, update);
    },

    // Add stats to the store
    add_stats(state, data) {
      state.stats = state.stats.concat(data.results);
      state.total_stats = data.count;
    },

    // Store check history
    use_history(state, data) {
      state.history = data;
    },

    // Store check issues
    use_check_issues(state, data) {
      state.check_issues = data;
    },
  },
  actions: {
    // Load Phabricator diffs from our backend
    // Load a single page at once, providing pagination state
    load_diffs(state, payload) {
      const url = payload.url || BACKEND_URL + "/v1/diff/";

      const params = payload.query || {};
      return axios.get(url, { params }).then((resp) => {
        state.commit("use_diffs", resp.data);
      });
    },

    // Load a specific diff and its issues
    load_diff(state, diffId) {
      const url = BACKEND_URL + "/v1/diff/" + diffId;
      state.commit("use_diff", null);
      return axios
        .get(url)
        .then((resp) => {
          state.commit("use_diff", resp.data);

          // Load all issues in that diff
          state.dispatch("load_issues", {
            diffId,
            url: resp.data.issues_url,
          });
        })
        .catch((err) => {
          state.commit("use_diff", err);
        });
    },

    load_issues(state, payload) {
      if (payload.url === null) {
        return;
      }

      axios.get(payload.url).then((resp) => {
        // Store new issues
        state.commit("add_issues", {
          diffId: payload.diffId,
          issues: resp.data.results,
        });

        // Load next issues
        payload.url = resp.data.next;
        state.dispatch("load_issues", payload);
      });
    },

    load_stats(state, payload) {
      if (payload.url === undefined) {
        state.commit("reset_stats");
      }
      const url = payload.url || BACKEND_URL + "/v1/check/stats/";

      const params = {};
      if (payload.since !== undefined) {
        params.since = payload.since;
      }

      // Remove null values from params
      Object.entries(params).forEach(([k, v]) => {
        if (v === null) delete params[k];
      });

      axios.get(url, { params }).then((resp) => {
        // Store new stats
        state.commit("add_stats", resp.data);

        // Load next stats
        if (resp.data.next !== null) {
          // Do not propagate since, as it's already included in the next
          state.dispatch("load_stats", { url: resp.data.next });
        }
      });
    },

    // Store new issues for that check
    load_check_issues(state, payload) {
      const url =
        payload.url ||
        BACKEND_URL +
          `/v1/check/${payload.repository}/${payload.analyzer}/${payload.check}/`;
      const params = {};
      if (payload.publishable !== undefined) {
        params.publishable = payload.publishable;
      }
      if (payload.since !== undefined) {
        params.since = payload.since;
      }
      axios.get(url, { params }).then((resp) => {
        state.commit("use_check_issues", resp.data);
      });
    },

    load_repositories(state, payload) {
      const url = BACKEND_URL + "/v1/repository/";

      return axios.get(url).then((resp) => {
        // Assume we only have one page here
        state.commit("use_repositories", resp.data.results);
      });
    },

    // Retrieve diff data stored in Taskcluster index
    // Do not persist that data in our store
    load_taskcluster_diff(state, payload) {
      const url = TASKCLUSTER_DIFF_INDEX + payload.id;
      return axios.get(url);
    },

    // Load a specific revision and its diffs
    load_revision(state, payload) {
      return Promise.all([
        axios.get(BACKEND_URL + "/v1/revision/" + payload.id),
        axios.get(BACKEND_URL + "/v1/revision/" + payload.id + "/diffs/"),
      ]).then(([respRevision, respDiffs]) => {
        // Store revision & diffs data
        state.commit("use_revision", {
          revision: respRevision.data,
          diffs: respDiffs.data.results,
        });

        // Start loading issues for each diff
        for (const diff of respDiffs.data.results) {
          state.dispatch("load_issues", {
            diffId: diff.id,
            url: diff.issues_url,
          });
        }
      });
    },

    // Load Phabricator indexed tasks summary from Taskcluster
    load_index(state, payload) {
      const channel = payload.channel || "production";
      let url = `https://firefox-ci-tc.services.mozilla.com/api/index/v1/tasks/project.relman.${channel}.code-review.phabricator.diff?limit=200`;
      if (payload && payload.continuationToken) {
        url += "&continuationToken=" + payload.continuationToken;
      }
      return axios.get(url).then((resp) => {
        state.commit("use_tasks", {
          tasks: resp.data.tasks,
          url,
        });

        // Continue loading available tasks
        if (resp.data.continuationToken) {
          state.dispatch("load_index", {
            channel,
            continuationToken: resp.data.continuationToken,
          });
        }
      });
    },

    load_history(state, payload) {
      const url = BACKEND_URL + "/v1/check/history/";
      const params = payload || {};

      // Reset
      state.commit("use_history", []);

      // Remove null values from params
      Object.entries(params).forEach(([k, v]) => {
        if (v === null) delete params[k];
      });

      return axios.get(url, { params }).then((resp) => {
        state.commit("use_history", resp.data);
      });
    },
  },
});

export default store;
