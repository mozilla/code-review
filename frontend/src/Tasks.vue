<script>
import mixins from './mixins.js'
import _ from 'lodash'
import Choice from './Choice.vue'

export default {
  mounted () {
    // Load new tasks at startup
    this.load_tasks()
  },
  watch: {
    '$route' (to, from, next) {
      // Load new tasks when route change
      this.load_tasks()
    }
  },
  methods: {
    load_tasks () {
      var payload = {}

      // Reset state
      this.$store.commit('reset')

      // Load a specific revision only
      if (this.$route.params.revision) {
        payload['revision'] = this.$route.params.revision
      }
      this.$store.dispatch('load_index', payload)
    }
  },
  components: {
    Choice: Choice
  },
  data: function () {
    return {
      filters: {
        state: null,
        issues: null,
        revision: null
      },
      choices: {
        issues: [
          {
            name: 'No issues',
            func: t => t.data.issues === undefined || t.data.issues === 0
          },
          {
            name: 'Has issues',
            func: t => t.data.issues && t.data.issues > 0
          },
          {
            name: 'Publishable issues',
            func: t => t.data.issues_publishable && t.data.issues_publishable > 0
          }
        ]
      }
    }
  },
  mixins: [
    mixins.date
  ],
  computed: {
    tasks () {
      let tasks = this.$store.state.tasks

      // Filter by states
      if (this.filters.state !== null) {
        tasks = _.filter(tasks, t => t.state_full === this.filters.state.key)
      }

      // Filter by issues
      if (this.filters.issues !== null) {
        tasks = _.filter(tasks, this.filters.issues.func)
      }

      // Filter by revision
      if (this.filters.revision !== null) {
        tasks = _.filter(tasks, t => {
          let payload = t.data.title + t.data.bugzilla_id + t.data.phid + t.data.diff_phid + t.data.id + t.data.diff_id
          return payload.toLowerCase().indexOf(this.filters.revision.toLowerCase()) !== -1
        })
      }

      return tasks
    },
    tasks_total () {
      return this.$store.state.tasks ? this.$store.state.tasks.length : 0
    },
    states () {
      return this.$store.state.states
    }
  }
}
</script>

<template>
  <section>

    <div class="states" >
      <div class="state columns" v-for="state in states">
        <div class="column is-one-third">
          <progress class="progress" :class="{'is-danger': state.key.startsWith('error') || state.key === 'killed', 'is-success': state.key == 'done', 'is-info': state.key != 'done' && !state.key.startsWith('error')}" :value="state.percent" max="100">{{ state.percent }}%</progress>
        </div>
        <div class="column is-one-third">
          <strong>{{ state.name }}</strong> - <span class="has-text-grey-light">{{ state.nb }}/{{ tasks_total }} tasks or {{ state.percent }}%</span>
        </div>
      </div>
    </div>

    <table class="table is-fullwidth">
      <thead>
        <tr>
          <td>#</td>
          <td>
            <input class="input" type="text" v-model="filters.revision" placeholder="Filter using phabricator, bugzilla Id or word, ..."/>
          </td>
          <td>
            <Choice :choices="states" name="state" v-on:new-choice="filters.state = $event"/>
          </td>
          <td>
            <Choice :choices="choices.issues" name="issue" v-on:new-choice="filters.issues = $event"/>
          </td>
          <td>Indexed</td>
          <td>Actions</td>
        </tr>
      </thead>

      <tbody>
        <tr v-for="task in tasks">
          <td>
            <a class="mono" :href="'https://tools.taskcluster.net/task-inspector/#' + task.taskId" target="_blank">{{ task.taskId }}</a>
          </td>

          <td>
            <p v-if="task.data.title">{{ task.data.title }}</p>
            <p class="has-text-danger" v-else>No title</p>
            <p>
              <small class="mono has-text-grey-light">{{ task.data.diff_phid}}</small> - diff {{ task.data.diff_id || 'unknown'     }}
            </p>
            <p>
              <small class="mono has-text-grey-light">{{ task.data.phid}}</small> - <router-link :to="{ name: 'revision', params: { revision: task.data.id }}">rev {{ task.data.id }}</router-link>
            </p>
          </td>

          <td>
            <span class="tag is-light" v-if="task.data.state == 'started'">Started</span>
            <span class="tag is-info" v-else-if="task.data.state == 'cloned'">Cloned</span>
            <span class="tag is-info" v-else-if="task.data.state == 'analyzing'">Analyzing</span>
            <span class="tag is-primary" v-else-if="task.data.state == 'analyzed'">Analyzed</span>
            <span class="tag is-danger" v-else-if="task.data.state == 'killed'">
              Killed for timeout
            </span>
            <span class="tag is-danger" v-else-if="task.data.state == 'error'" :title="task.data.error_message">
              Error: {{ task.data.error_code || 'unknown' }}
            </span>
            <span class="tag is-success" v-else-if="task.data.state == 'done'">Done</span>
            <span class="tag is-black" v-else>Unknown</span>
          </td>

          <td :class="{'has-text-success': task.data.issues_publishable > 0}">

            <span v-if="task.data.issues_publishable > 0">{{ task.data.issues_publishable }}</span>
            <span v-else-if="task.data.issues_publishable == 0">{{ task.data.issues_publishable }}</span>
            <span v-else>-</span>
            / {{ task.data.issues }}
          </td>

          <td>
            <span :title="task.data.indexed">{{ task.data.indexed|since }} ago</span>
          </td>
          <td>
            <a class="button is-link" :href="task.data.url" target="_blank">Phabricator</a>
            <a v-if="task.data.bugzilla_id" class="button is-dark" :href="'https://bugzil.la/' + task.data.bugzilla_id" target="_blank">Bugzilla</a>
            <router-link v-if="task.data.issues > 0" :to="{ name: 'task', params: { taskId : task.taskId }}" class="button is-primary">Issues</router-link>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style>
.mono{
  font-family: monospace;
}

div.states {
  margin-top: 1rem;
  margin-bottom: 2rem;
}

div.states div.column {
  padding: 0.2rem;
}

div.states div.column progress {
  margin-top: 0.3rem;
}

div.table input.input {
  display: inline-block;
}
</style>
