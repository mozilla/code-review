<script>
import mixins from './mixins.js'
import _ from 'lodash'
import Choice from './Choice.vue'

export default {
  mounted () {
    // Load new tasks at startup
    this.load_diffs()
  },
  watch: {
    '$route' (to, from, next) {
      // Load new tasks when route change
      if (to.path !== from.path) {
        this.load_diffs()
      }
    }
  },
  methods: {
    load_diffs () {
      var payload = {}

      // Reset state
      this.$store.commit('reset')

      // Load a specific revision only
      if (this.$route.params.revision) {
        payload['revision'] = this.$route.params.revision
      }
      this.$store.dispatch('load_diffs', payload)
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
        revision: null,
        repository: null
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
    diffs () {
      let diffs = this.$store.state.diffs.results

      // TODO: implement those filters on the backend

      // Filter by repository
      if (this.filters.repository !== null) {
        diffs = _.filter(diffs, t => t.revision.repository === this.filters.repository)
      }

      // Filter by states
      if (this.filters.state !== null) {
        diffs = _.filter(diffs, t => t.state_full === this.filters.state.key)
      }

      // Filter by issues
      if (this.filters.issues !== null) {
        diffs = _.filter(diffs, this.filters.issues.func)
      }

      // Filter by revision
      if (this.filters.revision !== null) {
        diffs = _.filter(diffs, t => {
          let payload = t.data.title + t.data.bugzilla_id + t.data.phid + t.data.diff_phid + t.data.id + t.data.diff_id
          return payload.toLowerCase().indexOf(this.filters.revision.toLowerCase()) !== -1
        })
      }

      return diffs
    },
    diffs_total () {
      return this.$store.state.diffs.count
    },
    states () {
      return this.$store.state.states
    },
    repositories () {
      // Convert repositories set to an array
      return [...this.$store.state.repositories].map(url => {
        if (url.startsWith('https://hg.mozilla.org/')) {
          return url.substring(23)
        }
        return url
      })
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
            <Choice :choices="repositories" name="repo" v-on:new-choice="filters.repository = $event"/>
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
        <tr v-for="diff in diffs">
          <td>
            Diff {{ diff.id }}
            <br />
            <a class="mono" :href="'https://firefox-ci-tc.services.mozilla.com/tasks/' + diff.review_task_id" target="_blank">{{ diff.review_task_id }}</a>
          </td>

          <td>
            <p v-if="diff.revision.title">{{ diff.revision.title }}</p>
            <p class="has-text-danger" v-else>No title</p>
            <p>
              <small class="mono has-text-grey-light">{{ diff.revision.phid}}</small> - <router-link :to="{ name: 'revision', params: { revision: diff.revision.id }}">rev {{ diff.revision.id }}</router-link>
            </p>
          </td>

          <td>
            <span class="tag is-primary" v-if="task.data.repository == 'https://hg.mozilla.org/mozilla-central'">Mozilla Central</span>
            <span class="tag is-info" v-else-if="task.data.repository == 'https://hg.mozilla.org/projects/nss'">NSS</span>
            <span class="tag is-dark" v-else>{{ task.data.repository || 'Unknown'}}</span>
          </td>

          <td>
            <span class="tag is-light" v-if="diff.state == 'started'">Started</span>
            <span class="tag is-info" v-else-if="diff.state == 'cloned'">Cloned</span>
            <span class="tag is-info" v-else-if="diff.state == 'analyzing'">Analyzing</span>
            <span class="tag is-primary" v-else-if="diff.state == 'analyzed'">Analyzed</span>
            <span class="tag is-danger" v-else-if="diff.state == 'killed'">
              Killed for timeout
            </span>
            <span class="tag is-danger" v-else-if="diff.state == 'error'" :title="diff.error_message">
              Error: {{ diff.error_code || 'unknown' }}
            </span>
            <span class="tag is-success" v-else-if="diff.state == 'done'">Done</span>
            <span class="tag is-black" v-else>Unknown</span>
          </td>

          <td :class="{'has-text-success': diff.issues_publishable > 0}">

            <span v-if="diff.issues_publishable > 0">{{ diff.issues_publishable }}</span>
            <span v-else-if="diff.issues_publishable == 0">{{ diff.issues_publishable }}</span>
            <span v-else>-</span>
            / {{ diff.nb_issues }}
          </td>

          <td>
            <span :title="diff.indexed">{{ diff.indexed|since }} ago</span>
          </td>
          <td>
<<<<<<< HEAD
            <a class="button is-link" :href="task.data.url" target="_blank">Phabricator</a>
            <a v-if="task.data.bugzilla_id" class="button is-dark" :href="'https://bugzil.la/' + task.data.bugzilla_id" target="_blank">Bugzilla</a>
            <a class="button is-primary" :href="'https://firefox-ci-tc.services.mozilla.com/tasks/' + task.data.try_group_id" target="_blank">Try Tasks</a>
            <router-link v-if="task.data.issues > 0" :to="{ name: 'task', params: { taskId : task.taskId }}" class="button is-primary">Issues</router-link>
=======
            <a class="button is-link" :href="diff.url" target="_blank">Phabricator</a>
            <a v-if="diff.revision.bugzilla_id" class="button is-dark" :href="'https://bugzil.la/' + diff.revision.bugzilla_id" target="_blank">Bugzilla</a>
            <a class="button is-primary" :href="'https://tools.taskcluster.net/tasks/' + diff.try_group_id" target="_blank">Try Tasks</a>
            <router-link v-if="diff.nb_issues > 0" :to="{ name: 'diff', params: { diffId: diff.id }}" class="button is-primary">Issues</router-link>
>>>>>>> frontend: load diffs on home page
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
