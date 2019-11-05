import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'
Vue.use(Vuex)

const TASKCLUSTER_DIFF_INDEX = 'https://index.taskcluster.net/v1/task/project.relman.production.code-review.phabricator.diff.'

export default new Vuex.Store({
  state: {
    backend_url: process.env.BACKEND_URL,
    diffs: [],
    stats: null,
    total_stats: 0, // Used to track download progress
    states: null,
    repositories: null,
    diff: null
  },
  mutations: {
    reset (state) {
      state.diffs = []
      state.diff = null
    },

    reset_stats (state) {
      state.stats = []
      state.total_stats = 0
    },

    use_diffs (state, diffs) {
      // Simply store diffs & their current pagination
      state.diffs = diffs
    },

    use_repositories (state, repositories) {
      // Simply store repositories directly
      state.repositories = repositories
    },

    // Store a new diff to display
    use_diff (state, diff) {
      state.diff = diff
      if (state.diff !== null) {
        state.diff.issues = []
      }
    },

    // Add issues to the currently stored diff
    add_issues (state, issues) {
      if (!state.diff) {
        return null
      }
      state.diff = Object.assign({}, state.diff, { 'issues': state.diff.issues.concat(issues) })
    },

    // Add stats to the store
    add_stats (state, data) {
      state.stats = state.stats.concat(data.results)
      state.total_stats = data.count
    }
  },
  actions: {
    // Load Phabricator diffs from our backend
    // Load a single page at once, providing pagination state
    load_diffs (state, payload) {
      let url = this.state.backend_url + '/v1/diff/'

      return axios.get(url).then(resp => {
        state.commit('use_diffs', resp.data)
      })
    },

    // Load a specific diff and its issues
    load_diff (state, diffId) {
      let url = this.state.backend_url + '/v1/diff/' + diffId
      state.commit('use_diff', null)
      return axios.get(url).then(resp => {
        state.commit('use_diff', resp.data)

        // Load all issues in that diff
        state.dispatch('load_issues', resp.data.issues_url)
      }).catch(err => {
        state.commit('use_diff', err)
      })
    },

    load_issues (state, issuesUrl) {
      if (issuesUrl === null) {
        return
      }
      if (this.state.diff === null) {
        throw new Error('Cannot load issues without a diff')
      }

      axios.get(issuesUrl).then(resp => {
        // Store new issues
        state.commit('add_issues', resp.data.results)

        // Load next issues
        state.dispatch('load_issues', resp.data.next)
      })
    },

    load_stats (state, url) {
      if (url === null) {
        return
      } else if (url === undefined) {
        state.commit('reset_stats')
        url = this.state.backend_url + '/v1/check/stats/'
      }

      axios.get(url).then(resp => {
        // Store new stats
        state.commit('add_stats', resp.data)

        // Load next stats
        state.dispatch('load_stats', resp.data.next)
      })
    },

    load_repositories (state, payload) {
      let url = this.state.backend_url + '/v1/repository/'

      return axios.get(url).then(resp => {
        // Assume we only have one page here
        state.commit('use_repositories', resp.data.results)
      })
    },

    // Retrieve diff data stored in Taskcluster index
    // Do not persist that data in our store
    load_taskcluster_diff (state, payload) {
      let url = TASKCLUSTER_DIFF_INDEX + payload.id
      return axios.get(url)
    }
  }
})
