<script>
import mixins from "./mixins.js";
import Choice from "./Choice.vue";
import Pagination from "./Pagination.vue";

export default {
  mounted() {
    // Use parameters from url as initial query
    if (this.$route.query) {
      this.$set(this, "query", Object.assign({}, this.$route.query));
    }

    // Load new tasks at startup
    this.$store.commit("reset");
    this.$store.dispatch("load_diffs", { query: this.query });

    // Load repositories at startup
    this.$store.dispatch("load_repositories");
  },
  components: {
    Choice,
    Pagination,
  },
  data: function () {
    return {
      query: {},
      choices: {
        issues: [
          { name: "No issues", value: "no" },
          { name: "Has issues", value: "any" },
          { name: "Publishable issues", value: "publishable" },
        ],
      },
    };
  },
  mixins: [mixins.date, mixins.query],
  methods: {
    use_filter(name, value) {
      // Filter current diffs query
      if (value) {
        this.query[name] = value;
      } else if (name in this.query) {
        delete this.query[name];
      }
      this.$set(this, "query", this.query);
      this.$store.dispatch("load_diffs", { query: this.query });

      // Update directly the router query with our filters
      this.$router.push({ query: this.query });
    },
    use_search(evt) {
      // Only submit on Enter key pressed
      if (evt.keyCode !== 13) {
        return;
      }
      this.use_filter("search", this.query.search);
    },
    reset_query() {
      this.$set(this, "query", {});
      this.$router.push({ query: {} });
      this.$store.dispatch("load_diffs", {});
    },
  },
  computed: {
    diffs() {
      if (!this.$store.state.diffs) {
        return [];
      }
      return this.$store.state.diffs.results;
    },
    repositories() {
      const repos = this.$store.state.repositories || [];
      return repos.map((r) => r.slug);
    },
  },
  filters: {
    treeherder_url(diff) {
      const rev = diff.mercurial_hash;
      const tryRepo =
        diff.revision.head_repository === "nss" ? "nss-try" : "try";
      return `https://treeherder.mozilla.org/#/jobs?repo=${tryRepo}&revision=${rev}`;
    },
    short_repo(url) {
      if (url.startsWith("https://hg.mozilla.org/")) {
        return url.substring(23);
      }
      return url;
    },
  },
};
</script>

<template>
  <section>
    <Pagination
      :api_data="$store.state.diffs"
      name="diffs"
      store_method="load_diffs"
    ></Pagination>

    <table class="table is-fullwidth">
      <thead>
        <tr>
          <td>#</td>
          <td>
            <input
              class="input"
              type="text"
              v-on:keyup="use_search($event)"
              v-model="query.search"
              placeholder="Filter using phabricator, bugzilla Id or word, ..."
            />
          </td>
          <td>
            <Choice
              :choices="repositories"
              name="repository"
              v-on:new-choice="use_filter('repository', $event)"
            />
          </td>
          <td>
            <Choice
              :choices="choices.issues"
              name="issues"
              v-on:new-choice="use_filter('issues', $event.value)"
            />
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
            <a
              class="mono"
              :href="
                'https://firefox-ci-tc.services.mozilla.com/tasks/' +
                diff.review_task_id
              "
              target="_blank"
              >{{ diff.review_task_id }}</a
            >
          </td>

          <td>
            <p v-if="diff.revision.title">{{ diff.revision.title }}</p>
            <p class="has-text-danger" v-else>No title</p>
            <p>
              Revision
              <router-link
                :to="{
                  name: 'revision',
                  params: { revisionId: diff.revision.id },
                }"
                >Revision {{ diff.revision.provider_id }}</router-link
              >
              @ base: {{ diff.revision.base_repository | short_repo }} - head:
              {{ diff.revision.head_repository | short_repo }}
            </p>
          </td>

          <td>
            <a
              :href="diff.repository.url + '/rev/' + diff.mercurial_hash"
              target="_blank"
              >{{ diff.mercurial_hash.substring(0, 8) }} @
              {{ diff.repository.slug }}</a
            >
          </td>

          <td :class="{ 'has-text-success': diff.nb_issues_publishable > 0 }">
            <p>
              <span
                v-if="diff.nb_issues_publishable > 0"
                class="tag is-success is-light"
                >{{ diff.nb_issues_publishable }} publishable</span
              >
            </p>
            <p>
              <span v-if="diff.nb_warnings > 0" class="tag is-warning is-light"
                >{{ diff.nb_warnings }} warnings</span
              >
            </p>
            <p>
              <span v-if="diff.nb_errors > 0" class="tag is-danger is-light"
                >{{ diff.nb_errors }} errors</span
              >
            </p>
          </td>

          <td>
            <span :title="diff.created">{{ diff.created | since }} ago</span>
          </td>
          <td>
            <div class="buttons">
              <router-link
                class="button is-primary is-small"
                v-if="diff.nb_issues > 0"
                :to="{ name: 'diff', params: { diffId: diff.id } }"
                >➕ Issues</router-link
              >
              <div class="dropdown is-hoverable">
                <div class="dropdown-trigger">
                  <button
                    class="button is-dark is-small"
                    aria-haspopup="true"
                    aria-controls="dropdown-menu4"
                  >
                    <span>🔩 Details</span>
                  </button>
                </div>
                <div class="dropdown-menu" id="dropdown-menu4" role="menu">
                  <div class="dropdown-content">
                    <hr class="dropdown-divider" />
                    <a
                      v-if="revision.provider == 'phabricator'"
                      class="dropdown-item"
                      :href="diff.revision.url"
                      target="_blank"
                      >Phabricator D{{ diff.revision.provider_id }}</a
                    >
                    <a
                      v-if="revision.provider == 'github'"
                      class="dropdown-item"
                      :href="diff.revision.url"
                      target="_blank"
                      >Github PR n°{{ diff.revision.provider_id }}</a
                    >
                    <a
                      class="dropdown-item"
                      v-if="diff.revision.bugzilla_id"
                      :href="'https://bugzil.la/' + diff.revision.bugzilla_id"
                      target="_blank"
                      >Bug {{ diff.revision.bugzilla_id }}</a
                    >
                    <a
                      class="dropdown-item"
                      :href="diff | treeherder_url"
                      target="_blank"
                      >Treeherder tasks</a
                    >
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div
      class="notification is-light"
      v-if="diffs && diffs.length == 0 && query"
    >
      <p class="is-inline-block has-text-weight-medium">
        Sorry, no diffs are available for your search terms !
      </p>
      <button
        class="is-inline-block button is-success"
        v-on:click="reset_query()"
      >
        Reset search
      </button>
    </div>
  </section>
</template>

<style>
.mono {
  font-family: monospace;
}

div.table input.input {
  display: inline-block;
}
</style>
