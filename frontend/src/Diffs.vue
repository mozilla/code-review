<script>
import mixins from './mixins.js'
import Choice from './Choice.vue'

export default {
  mounted () {
    // Use parameters from url as initial query
    if (this.$route.query) {
      this.$set(this, 'filters', this.$route.query)
      this.$set(this, 'search', this.filters.search)
    }

    // Load new tasks at startup
    this.$store.commit('reset')
    this.$store.dispatch('load_diffs', { filters: this.filters })

    // Load repositories at startup
    this.$store.dispatch('load_repositories')
  },
  components: {
    Choice: Choice
  },
  data: function () {
    return {
      search: null,
      filters: {},
      choices: {
        issues: [
          {
            name: 'No issues',
            filter: 'no_issues'
          },
          {
            name: 'Has issues',
            filter: 'has_issues'
          },
          {
            name: 'New issues',
            filter: 'new_issues'
          }
        ]
      }
    }
  },
  mixins: [
    mixins.date,
    mixins.query
  ],
  methods: {
    load_next_diffs () {
      if (!this.has_next) {
        return
      }

      this.$store.dispatch('load_diffs', {
        url: this.$store.state.diffs.next
      })
    },
    load_previous_diffs () {
      if (!this.has_previous) {
        return
      }

      this.$store.dispatch('load_diffs', {
        url: this.$store.state.diffs.previous
      })
    },
    use_filter (name, value) {
      // Filter current diffs query
      if (value) {
        this.filters[name] = value
      } else if (name in this.filters) {
        delete this.filters[name]
      }
      this.$set(this, 'filters', this.filters)
      this.$store.dispatch('load_diffs', { filters: this.filters })

      this.$router.push({ query: this.filters })
    },
    use_search (evt) {
      // Only submit on Enter key pressed
      if (evt.keyCode !== 13) {
        return
      }

      this.use_filter('search', this.search)
    }
  },
  computed: {
    diffs () {
      return this.$store.state.diffs.results
    },
    states () {
      return this.$store.state.states
    },
    repositories () {
      let repos = this.$store.state.repositories || []
      return repos.map(r => r.slug)
    },

    // Pagination helper
    total () {
      return this.$store.state.diffs.count
    },
    has_next () {
      return this.$store.state.diffs.next !== null
    },
    has_previous () {
      return this.$store.state.diffs.previous !== null
    }
  },
  filters: {
    treeherder_url (diff) {
      let rev = diff.mercurial_hash
      let tryRepo = diff.revision.repository === 'nss' ? 'nss-try' : 'try'
      return `https://treeherder.mozilla.org/#/jobs?repo=${tryRepo}&revision=${rev}`
    }
  }
}
</script>

<template>
  <section>
  <pre>{{ filters }}</pre>

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

    <nav class="pagination" v-if="total > 0">
      <button class="pagination-previous" :disabled="!has_previous" v-on:click="load_previous_diffs">Newer diffs</button>
      <button class="pagination-next" :disabled="!has_next" v-on:click="load_next_diffs">Older diffs</button>
    </nav>

    <table class="table is-fullwidth">
      <thead>
        <tr>
          <td>#</td>
          <td>
            <input class="input" type="text" v-on:keyup="use_search($event)" v-model="search" placeholder="Filter using phabricator, bugzilla Id or word, ..."/>
          </td>
          <td>
            <Choice :choices="repositories" name="repository" v-on:new-choice="use_filter('repository', $event)"/>
          </td>
          <!--
          <td>
            <Choice :choices="states" name="state" v-on:new-choice="use_filter('state', $event)"/>
          </td>
          -->
          <td>
            <Choice :choices="choices.issues" name="issue" v-on:new-choice="use_filter('issues', $event.filter)"/>
          </td>
          <td>Created</td>
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
              Revision <router-link :to="{ name: 'revision', params: { revisionId: diff.revision.id }}">D{{ diff.revision.id }}</router-link>
            </p>
          </td>

          <td>
            <span class="tag is-primary" v-if="task.data.repository == 'https://hg.mozilla.org/mozilla-central'">Mozilla Central</span>
            <span class="tag is-info" v-else-if="task.data.repository == 'https://hg.mozilla.org/projects/nss'">NSS</span>
            <span class="tag is-dark" v-else>{{ task.data.repository || 'Unknown'}}</span>
          </td>

          <!--
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
          -->

          <td :class="{'has-text-success': diff.nb_issues_new_for_revision > 0}">

            <span v-if="diff.nb_issues_new_for_revision > 0">{{ diff.nb_issues_new_for_revision }}</span>
            <span v-else-if="diff.nb_issues_new_for_revision == 0">{{ diff.nb_issues_new_for_revision }}</span>
            <span v-else>-</span>
            / {{ diff.nb_issues }}
          </td>

          <td>
            <span :title="diff.created">{{ diff.created|since }} ago</span>
          </td>
          <td>
            <a class="button is-link" :href="diff.revision.phabricator_url" target="_blank">Phabricator</a>
            <a v-if="diff.revision.bugzilla_id" class="button is-dark" :href="'https://bugzil.la/' + diff.revision.bugzilla_id" target="_blank">Bugzilla</a>
            <a class="button is-primary" :href="diff | treeherder_url" target="_blank">Treeherder</a>
            <router-link v-if="diff.nb_issues > 0" :to="{ name: 'diff', params: { diffId: diff.id }}" class="button is-primary">Issues</router-link>
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
