import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'
Vue.use(Vuex)

const FINAL_STATES = ['done', 'error']

// Must stay in sync with src/staticanalysis/bot/default.nix maxRunTime & deadline parameters
// This is currently set to 2 hours in ms
const MAX_TTL = 2 * 3600 * 1000

export default new Vuex.Store({
  state: {
    backend_url: process.env.BACKEND_URL,
    diffs: [],
    indexes: [],
    stats: {
      loaded: 0,
      errors: 0,
      ids: [],
      checks: {},
      start_date: new Date()
    },
    states: null,
    repositories: new Set(),
    diff: null
  },
  mutations: {
    reset (state) {
      state.diffs = []
      state.diff = null
      state.indexes = []
      state.stats = {
        loaded: 0,
        errors: 0,
        ids: [],
        checks: {},
        start_date: new Date()
      }
    },

    use_diffs (state, diffs) {
      // Simply store diffs & their current pagination
      state.diffs = diffs
    },

    use_tasks (state, payload) {
      var now = new Date()

      // Save url
      state.indexes.push(payload.url)

      // Filter tasks without extra data
      let currentTasks = state.tasks.concat(
        payload.tasks.filter(task => task.data.indexed !== undefined)
      )

      currentTasks.map(task => {
        // Add a descriptive state key name to tasks
        task.state_full = task.data.state
        if (task.state_full === 'error' && task.data.error_code) {
          task.state_full += '.' + task.data.error_code
        }

        // Detect and update invalid state when a task got killed by Taskcluster
        let date = new Date(task.data.indexed)
        if (now - date > MAX_TTL && FINAL_STATES.indexOf(task.data.state) === -1) {
          task.data.state = 'killed'
          task.state_full = 'killed'
        }

        // Use full urls for old style slugs
        if (task.data.repository === 'mozilla-central') {
          task.data.repository = 'https://hg.mozilla.org/mozilla-central'
        } else if (task.data.repository === 'nss') {
          task.data.repository = 'https://hg.mozilla.org/projects/nss'
        }

        return task
      })

      // Sort by indexation date
      currentTasks.sort((x, y) => {
        return new Date(y.data.indexed) - new Date(x.data.indexed)
      })

      // Crunch stats about status
      let states = {}
      states = currentTasks.reduce((states, task) => {
        if (states[task.state_full] === undefined) {
          states[task.state_full] = 0
        }
        states[task.state_full] += 1
        return states
      }, states)

      // Save tasks
      state.tasks = currentTasks

      // Order states by their nb, and calc percents
      state.states = Object.keys(states).map(state => {
        let nb = states[state]
        return {
          'key': state,
          'name': state.startsWith('error.') ? 'error: ' + state.substring(6) : state,
          'nb': nb,
          'percent': currentTasks && currentTasks.length > 0 ? Math.round(nb * 100 / currentTasks.length) : 0
        }
      }).sort((x, y) => { return y.nb - x.nb })

      // Update repositories reference
      state.repositories = new Set(state.tasks.map(t => t.data.repository).filter(x => x))

      // List all active tasks Ids for stats calculations
      state.stats.ids = state.stats.ids.concat(
        payload.tasks
          .filter((task) => task.data.state === 'done' && task.data.issues > 0)
          .map(t => t.taskId)
      )
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
    }
  }
})
