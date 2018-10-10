import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'
import router from './routes'
Vue.use(Vuex)

const PREFERENCES_KEY = 'mozilla-sa-dashboard'
const TASKCLUSTER_INDEX = 'https://index.taskcluster.net/v1'
const TASKCLUSTER_QUEUE = 'https://queue.taskcluster.net/v1'
const TASKS_SLICE = 10

export default new Vuex.Store({
  state: {
    channel: 'production',
    tasks: [],
    report: null,
    stats: null,
    states: null
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
      state.stats = null
      state.report = null
      this.commit('save_preferences')
    },
    reset_tasks (state) {
      state.tasks = []
    },
    reset_stats (state) {
      // List all active tasks Ids
      var ids =
        state.tasks
          .filter((task) => task.data.state === 'done' && task.data.issues > 0)
          .map(t => t.taskId)

      state.stats = {
        loaded: 0,
        ids: ids,
        checks: {},
        start_date: new Date()
      }
    },
    use_tasks (state, tasks) {
      // Filter tasks without extra data
      let currentTasks = state.tasks.concat(
        tasks.filter(task => task.data.indexed !== undefined)
      )

      // Add a descriptive state key name to tasks
      currentTasks.map(task => {
        task.state_full = task.data.state
        if (task.state_full === 'error' && task.data.error_code) {
          task.state_full += '.' + task.data.error_code
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
    },
    use_report (state, report) {
      state.report = report

      if (report !== null && state.stats !== null) {
        // Calc stats for this report
        // clang-format does not provide any check information
        var checks = report.issues.filter(i => i.analyzer !== 'clang-format')
        state.stats.checks = checks.reduce((stats, issue) => {
          var analyzer = issue.analyzer + (issue.analyzer === 'mozlint' ? '.' + issue.linter : '')
          var check = issue.analyzer === 'clang-tidy' ? issue.check : issue.rule
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
    load_index (state) {
      state.commit('reset_tasks')
      let url = TASKCLUSTER_INDEX + '/tasks/project.releng.services.project.' + this.state.channel + '.static_analysis_bot.phabricator'
      return axios.get(url).then(resp => {
        state.commit('use_tasks', resp.data.tasks)
      })
    },

    // Load the report for a given task
    load_report (state, taskId) {
      let url = TASKCLUSTER_QUEUE + '/task/' + taskId + '/artifacts/public/results/report.json'
      state.commit('use_report', null)
      return axios.get(url).then(resp => {
        state.commit('use_report', Object.assign({ taskId }, resp.data))
      })
    },

    // Load multiple reports for stats crunching
    calc_stats (state, tasksId) {
      // Avoid multiple loads
      if (state.state.stats !== null) {
        return
      }

      // Load all indexes to get task ids
      var indexes = state.dispatch('load_index')
      indexes.then(() => {
        console.log('Start analysis')
        state.commit('reset_stats')

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
      var batch = Promise.all(slice.map(taskId => state.dispatch('load_report', taskId)))
      batch.then(resp => console.info('Loaded batch', step))
      batch.then(resp => state.dispatch('load_report_batch', step + 1))
    }
  }
})
