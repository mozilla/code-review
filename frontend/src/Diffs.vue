<script>
import mixins from './mixins.js'
import Choice from './Choice.vue'

export default {
  mounted () {
    // Use parameters from url as initial query
    if (this.$route.query) {
      this.$set(this, 'query', Object.assign({}, this.$route.query))
    }

    // Load new tasks at startup
    this.$store.commit('reset')
    this.$store.dispatch('load_diffs', { query: this.query })

    // Load repositories at startup
    this.$store.dispatch('load_repositories')
  },
  components: {
    Choice: Choice
  },
  data: function () {
    return {
      query: {},
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
        this.query[name] = value
      } else if (name in this.query) {
        delete this.query[name]
      }
      this.$set(this, 'query', this.query)
      this.$store.dispatch('load_diffs', { query: this.query })

      // Update directly the router query with our filters
      this.$router.push({ query: this.query })
    },
    use_search (evt) {
      // Only submit on Enter key pressed
      if (evt.keyCode !== 13) {
        return
      }
      this.use_filter('search', this.query.search)
    },
    reset_query () {
      this.$set(this, 'query', {})
      this.$router.push({ query: {} })
      this.$store.dispatch('load_diffs', {})
    }
  },
  computed: {
    diffs () {
      if (!this.$store.state.diffs) {
        return []
      }
      return this.$store.state.diffs.results
    },
    repositories () {
      let repos = this.$store.state.repositories || []
      return repos.map(r => r.slug)
    },

    // Pagination helper
    total () {
      return this.$store.state.diffs.count
    },
    page_nb () {
      return this.$store.state.diffs.results.length
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
    <nav class="columns" v-if="total > 0">
      <div class="column is-4 is-offset-8">
        <button class="button is-pulled-right is-dark" :disabled="!has_next" v-on:click="load_next_diffs">Older diffs ↣</button>
        <button class="button is-pulled-right is-dark" :disabled="!has_previous" v-on:click="load_previous_diffs">↞ Newer diffs</button>
        <div class="is-text-dark is-pulled-right">Showing {{ page_nb }}/{{ total }} Diffs</div>
      </div>
    </nav>

    <table class="table is-fullwidth">
      <thead>
        <tr>
          <td>#</td>
          <td>
            <input class="input" type="text" v-on:keyup="use_search($event)" v-model="query.search" placeholder="Filter using phabricator, bugzilla Id or word, ..."/>
          </td>
          <td>
            <Choice :choices="repositories" name="repository" v-on:new-choice="use_filter('repository', $event)"/>
          </td>
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

          <td :class="{'has-text-success': diff.nb_issues_new_for_revision > 0}">
            <span v-if="diff.nb_issues_new_for_revision >= 0">{{ diff.nb_issues_new_for_revision }}</span>
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

    <div class="notification is-light" v-if="diffs && diffs.length == 0 && query">
      <p class="is-inline-block has-text-weight-medium">Sorry, no diffs are available for your search terms !</p>
      <button class="is-inline-block button is-success" v-on:click="reset_query()">Reset search</button>
    </div>
  </section>
</template>

<style>
.mono{
  font-family: monospace;
}

nav.columns {
  margin-top: 12px;
}

nav.columns * {
  margin-left: 10px;
}

nav.columns div {
  padding-top: 5px;
}

div.table input.input {
  display: inline-block;
}
</style>
