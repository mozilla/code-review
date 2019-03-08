import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'
import router from './routes'
Vue.use(Vuex)

const PREFERENCES_KEY = 'mozilla-sa-dashboard'
const TASKCLUSTER_INDEX = 'https://index.taskcluster.net/v1'
const TASKCLUSTER_QUEUE = 'https://queue.taskcluster.net/v1'
const TASKS_SLICE = 10
const FINAL_STATES = ['done', 'error']

// Must stay in sync with src/staticanalysis/bot/default.nix maxRunTime & deadline parameters
// This is currently set to 2 hours in ms
const MAX_TTL = 2 * 3600 * 1000

export default new Vuex.Store({
  state: {
    channel: 'production',
    tasks: [],
    indexes: [],
    stats: {
      loaded: 0,
      errors: 0,
      ids: [],
      checks: {},
      start_date: new Date()
    },
    states: null,
    report: null
  },
  mutations: {
    load_preferences (state) {
      // Load prefs from local storage
      let rawPrefs = localStorage.getItem(PREFERENCES_KEY)
      if (rawPrefs) {
        let prefs = JSON.parse(rawPrefs)
        if (prefs.channel) {
          state.channel = prefs.channel
        }
      }
    },
    save_preferences (state) {
      // Save channel to preferences
      localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
        channel: state.channel
      }))
    },
    use_channel (state, channel) {
      state.channel = channel
      this.commit('reset')
      this.commit('save_preferences')
    },
    reset (state) {
      state.tasks = []
      state.indexes = []
      state.stats = {
        loaded: 0,
        errors: 0,
        ids: [],
        checks: {},
        start_date: new Date()
      }
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
          var analyzer = issue.analyzer + (issue.analyzer === 'mozlint' ? '.' + issue.linter : '')
          var check = null
          if (issue.analyzer === 'clang-tidy') {
            check = issue.check
          } else if (issue.analyzer === 'clang-format') {
            check = 'lint' // No check informations on clang-format
          } else if (issue.analyzer === 'infer') {
            check = issue.bug_type
          } else if (issue.analyzer === 'mozlint') {
            check = issue.rule
          } else if (issue.analyzer === 'Coverity') {
            check = issue.kind
          } else if (issue.analyzer === 'coverage') {
            check = '0 coverage'
          } else {
            console.warn('Unsupported analyzer', issue.analyzer)
            return
          }
          var key = analyzer + '.' + check
          if (stats[key] === undefined) {
            stats[key] = {
              analyzer: analyzer,
              key: key,
              message: issue.message,
              check: check,
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
    // Switch data channel to use
    switch_channel (state, channel) {
      state.commit('use_channel', channel)
      state.dispatch('load_index')
      router.push({ name: 'tasks' })
    },

    // Load Phabricator indexed tasks summary from Taskcluster
    load_index (state, payload) {
      let url = TASKCLUSTER_INDEX + '/tasks/project.releng.services.project.' + this.state.channel + '.static_analysis_bot.phabricator.'
      if (payload && payload.revision) {
        // Remove potential leading 'D' from phabricator revision
        url += !Number.isInteger(payload.revision) && payload.revision.startsWith('D') ? payload.revision.substring(1) : payload.revision
      } else {
        url += 'diff'
      }

      url += '?limit=200'
      if (payload && payload.continuationToken) {
        url += '&continuationToken=' + payload.continuationToken
      }
      if (state.state.indexes.includes(url)) {
        console.debug('Already loaded', url)
        return
      }
      return axios.get(url).then(resp => {
        state.commit('use_tasks', {
          tasks: resp.data.tasks,
          url: url
        })

        // Continue loading available tasks
        if (resp.data.continuationToken) {
          state.dispatch('load_index', { continuationToken: resp.data.continuationToken })
        }
      })
    },

    // Load the report for a given task
    load_report (state, taskId) {
      let url = TASKCLUSTER_QUEUE + '/task/' + taskId + '/artifacts/public/results/report.json'
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

      // Slice full loading in smaller batches to avoid using too many ressources
      var slice = state.state.stats.ids.slice(step * TASKS_SLICE, (step + 1) * TASKS_SLICE)
      var batch = Promise.all(
        slice.map(taskId => state.dispatch('load_report', taskId))
      )
      batch.then(resp => console.info('Loaded batch', step))
      batch.then(resp => state.dispatch('load_report_batch', step + 1))
    }
  }
})
