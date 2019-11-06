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
    diff: null,
    issues: {},
    revision: null
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

    use_revision (state, payload) {
      state.revision = Object.assign(payload.revision, { 'diffs': payload.diffs })
    },

    // Store a new diff to display
    use_diff (state, diff) {
      state.diff = diff
      if (state.diff !== null) {
        state.diff.issues = []
      }
    },

    // Add issues to a diff
    add_issues (state, payload) {
      let update = {}
      let issues = state.issues[payload.diffId] || []
      update[payload.diffId] = issues.concat(payload.issues)
      state.issues = Object.assign({}, state.issues, update)
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
      let url = payload.url || this.state.backend_url + '/v1/diff/'

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
        state.dispatch('load_issues', {
          diffId: diffId,
          url: resp.data.issues_url
        })
      }).catch(err => {
        state.commit('use_diff', err)
      })
    },

    load_issues (state, payload) {
      if (payload.url === null) {
        return
      }

      axios.get(payload.url).then(resp => {
        // Store new issues
        state.commit('add_issues', {
          diffId: payload.diffId,
          issues: resp.data.results
        })

        // Load next issues
        payload.url = resp.data.next
        state.dispatch('load_issues', payload)
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
    },

    // Load a specific revision and its diffs
    load_revision (state, payload) {
      return Promise.all([
        axios.get(this.state.backend_url + '/v1/revision/' + payload.id),
        axios.get(this.state.backend_url + '/v1/revision/' + payload.id + '/diffs/')
      ]).then(([respRevision, respDiffs]) => {
        // Store revision & diffs data
        state.commit('use_revision', {
          revision: respRevision.data,
          diffs: respDiffs.data.results
        })

        // Start loading issues for each diff
        for (let diff of respDiffs.data.results) {
          state.dispatch('load_issues', {
            diffId: diff.id,
            url: diff.issues_url
          })
        }
      })
    }
  }
})
