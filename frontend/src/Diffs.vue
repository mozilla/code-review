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
          { name: 'No issues', value: 'no' },
          { name: 'Has issues', value: 'any' },
          { name: 'New issues', value: 'new' }
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
    },
    short_repo (url) {
      if (url.startsWith('https://hg.mozilla.org/')) {
        return url.substring(23)
      }
      return url
    }
  }
}
</script>

<template>
  <section>
    <nav class="columns" v-if="total > 0">
      <div class="column is-6 is-offset-6">
        <button class="button is-pulled-right is-dark" :disabled="!has_next" v-on:click="load_next_diffs">Older diffs ↣</button>
        <button class="button is-pulled-right is-dark" :disabled="!has_previous" v-on:click="load_previous_diffs">↞ Newer diffs</button>
        <button class="button is-pulled-right is-success" v-if="Object.keys(query).length > 0" v-on:click="reset_query()">Reset search</button>
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
            <Choice :choices="choices.issues" name="issues" v-on:new-choice="use_filter('issues', $event.value)"/>
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
              Revision <router-link :to="{ name: 'revision', params: { revisionId: diff.revision.id }}">D{{ diff.revision.id }}</router-link> @ {{ diff.revision.repository | short_repo }}
            </p>
          </td>

          <td>
            <a :href="diff.repository.url + '/rev/' + diff.mercurial_hash" target="_blank">{{ diff.mercurial_hash.substring(0, 8) }} @ {{ diff.repository.slug }}</a>
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
            <div class="buttons">
              <router-link class="button is-primary is-small" v-if="diff.nb_issues > 0" :to="{ name: 'diff', params: { diffId: diff.id }}">➕ Issues</router-link>
              <div class="dropdown is-hoverable">
                <div class="dropdown-trigger">
                  <button class="button is-dark is-small" aria-haspopup="true" aria-controls="dropdown-menu4">
                    <span>🔩 Details</span>
                  </button>
                </div>
                <div class="dropdown-menu" id="dropdown-menu4" role="menu">
                  <div class="dropdown-content">
                    <hr class="dropdown-divider">
                    <a class="dropdown-item" :href="diff.revision.phabricator_url" target="_blank">Phabricator D{{ diff.revision.id }}</a>
                    <a class="dropdown-item" v-if="diff.revision.bugzilla_id" :href="'https://bugzil.la/' + diff.revision.bugzilla_id" target="_blank">Bug {{ diff.revision.bugzilla_id }}</a>
                    <a class="dropdown-item" :href="diff | treeherder_url" target="_blank">Treeherder tasks</a>
                  </div>
                </div>
              </div>
            </div>
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
