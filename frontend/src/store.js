import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'
Vue.use(Vuex)

const TASKCLUSTER_ROOT_URL = 'https://firefox-ci-tc.services.mozilla.com/'
const TASKS_SLICE = 10
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
    report: null
  },
  mutations: {
    reset (state) {
      state.diffs = []
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
    use_report (state, report) {
      if (report === null) {
        return
      }

      // Save raw report for issues listing
      state.report = report

      if (report.response && report.response.status !== 200) {
        // Manage errors
        state.stats.errors += 1
        return
      }

      if (state.stats !== null && report.issues) {
        // Calc stats for this report
        state.stats.checks = report.issues.reduce((stats, issue) => {
          let key = issue.analyzer + '.' + issue.check
          if (stats[key] === undefined) {
            stats[key] = {
              analyzer: issue.analyzer,
              key: key,
              message: issue.message,
              check: issue.check,
              publishable: 0,
              issues: [],
              total: 0
            }
          }
          stats[key].publishable += issue.publishable ? 1 : 0
          stats[key].total++

          // Save publishable issues for Check component
          // and link report data to the issue
          if (issue.publishable) {
            let extras = {
              revision: report.revision,
              taskId: report.taskId
            }
            stats[key].issues.push(Object.assign(extras, issue))
          }
          return stats
        }, state.stats.checks)

        // Save start date
        state.stats.start_date = new Date(Math.min(new Date(report.time * 1000.0), state.stats.start_date))

        // Mark new report loaded
        state.stats.loaded += 1
      }
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

    // Load the report for a given task
    load_report (state, taskId) {
      let url = TASKCLUSTER_ROOT_URL + 'api/queue/v1/task/' + taskId + '/artifacts/public/results/report.json'
      state.commit('use_report', null)
      return axios.get(url).then(resp => {
        state.commit('use_report', Object.assign({ taskId }, resp.data))
      }).catch(err => {
        state.commit('use_report', err)
      })
    },

    // Load multiple reports for stats crunching
    calc_stats (state, tasksId) {
      // Avoid multiple loads
      if (state.state.stats.loaded > 0) {
        return
      }

      // Load all indexes to get task ids
      // and avoid reloading tasks
      var indexes = state.state.tasks.length > 0 ? Promise.resolve(true) : state.dispatch('load_index')
      indexes.then(() => {
        console.log('Start analysis')

        // Start processing by batches
        state.dispatch('load_report_batch', 0)
      })
    },
    load_report_batch (state, step) {
      if (step * TASKS_SLICE > state.state.stats.ids.length) {
        return
      }

      // Slice full loading in smaller batches to avoid using too many resources
      var slice = state.state.stats.ids.slice(step * TASKS_SLICE, (step + 1) * TASKS_SLICE)
      var batch = Promise.all(
        slice.map(taskId => state.dispatch('load_report', taskId))
      )
      batch.then(resp => console.info('Loaded batch', step))
      batch.then(resp => state.dispatch('load_report_batch', step + 1))
    }
  }
})
