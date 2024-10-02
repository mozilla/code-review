<script>
import Bool from "./Bool.vue";
import Choice from "./Choice.vue";

export default {
  name: "Issues",
  data() {
    return {
      state: "loading",
      filters: {
        publishable: null,
        analyzer: null,
        path: null,
      },
      choices: {
        publishable: [
          {
            name: "Publishable",
            func: (i) => i.publishable,
          },
          {
            name: "Not publishable",
            func: (i) => !i.publishable,
          },
        ],
      },
    };
  },
  components: {
    Bool,
    Choice,
  },
  mounted() {
    // Update filters from query string
    const newForRevision = parseInt(this.$route.query.issue);
    this.filters.publishable = isNaN(newForRevision)
      ? null
      : this.choices.publishable[newForRevision];
    this.filters.path = this.$route.query.path || null;
    this.filters.analyzer = this.$route.query.analyzer || null;

    // Load diff
    const diff = this.$store.dispatch("load_diff", this.$route.params.diffId);
    diff.then(
      (response) => {
        this.$set(this, "state", "loaded");
      },
      (error) => {
        this.$set(
          this,
          "state",
          error.response.status === 404 ? "missing" : "error"
        );
      }
    );
  },
  computed: {
    diff() {
      return this.$store.state.diff;
    },
    paths() {
      // List sorted unique paths as choices
      const uniquePaths = new Set(this.all_issues.map((i) => i.path));
      return [...uniquePaths].sort();
    },
    analyzers() {
      // List sorted unique analyzers as choices
      const uniqueAnalyzers = new Set(this.all_issues.map((i) => i.analyzer));
      return [...uniqueAnalyzers].sort();
    },
    nb_publishable() {
      if (!this.diff || !this.diff.issues) {
        return 0;
      }
      return this.all_issues.filter((i) => i.publishable).length;
    },
    all_issues() {
      return this.diff ? this.$store.state.issues[this.diff.id] || [] : [];
    },
    issues() {
      let issues = this.all_issues;

      // Filter by publishable
      if (this.filters.publishable !== null) {
        issues = issues.filter(this.filters.publishable.func);
      }

      // Filter by path
      if (this.filters.path !== null) {
        issues = issues.filter((i) => i.path === this.filters.path);
      }

      // Filter by analyzer
      if (this.filters.analyzer !== null) {
        issues = issues.filter((i) => i.analyzer === this.filters.analyzer);
      }

      return issues;
    },
  },
  methods: {
    from_timestamp(value) {
      return new Date(value * 1000).toUTCString();
    },
  },
};
</script>

<template>
  <div>
    <h1 class="title">Diff {{ $route.params.diffId }}</h1>

    <div class="notification is-info" v-if="state == 'loading'">
      Loading diff...
    </div>
    <div class="notification is-warning" v-else-if="state == 'missing'">
      No diff, so no issues !
    </div>
    <div class="notification is-danger" v-else-if="state == 'error'">
      Failure
    </div>
    <div v-else-if="state == 'loaded'">
      <nav class="level" v-if="diff && diff.id">
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Publishable</p>
            <p class="title">{{ nb_publishable }}</p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Issues</p>
            <p class="title">{{ all_issues.length }}</p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Source</p>
            <p class="title">
              <a :href="diff.revision.url" target="_blank">{{
                diff.revision.title
              }}</a>
            </p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Diffed</p>
            <p class="title">{{ from_timestamp(diff.time) }}</p>
          </div>
        </div>
      </nav>

      <table class="table is-fullwidth" v-if="issues">
        <thead>
          <tr>
            <td>Hash</td>
            <td>
              <Choice
                :choices="analyzers"
                name="analyzer"
                v-on:new-choice="filters.analyzer = $event"
              />
            </td>
            <td>
              <Choice
                :choices="paths"
                name="path"
                v-on:new-choice="filters.path = $event"
              />
            </td>
            <td>Lines</td>
            <td>
              <Choice
                :choices="choices.publishable"
                name="publishable"
                v-on:new-choice="filters.publishable = $event"
              />
            </td>
            <td>Check</td>
            <td>Level</td>
            <td>Message</td>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="issue in issues"
            :class="{ publishable: issue.publishable }"
          >
            <td>
              <samp>{{ issue.hash.substring(0, 12) }}</samp>
            </td>
            <td>
              <span>{{ issue.analyzer }}</span>
            </td>
            <td class="path">{{ issue.path }}</td>
            <td>
              {{ issue.line }}
              <span v-if="issue.nb_lines > 1"
                >&rarr; {{ issue.line - 1 + issue.nb_lines }}</span
              >
            </td>
            <td>
              <p>
                <Bool :value="issue.publishable" name="Publishable" />
              </p>
              <p>
                <Bool :value="issue.new_for_revision" name="New for revision" />
              </p>
              <p>
                <Bool :value="issue.in_patch" name="In Patch" />
              </p>
            </td>

            <td>
              <span>{{ issue.check }}</span>
            </td>
            <td>
              <span v-if="issue.level == 'error'" class="tag is-danger"
                >Error</span
              >
              <span v-else-if="issue.level == 'warning'" class="tag is-warning"
                >Warning</span
              >
              <span v-else class="tag is-dark">{{ issue.level }}</span>
            </td>
            <td>
              <pre>{{ issue.message }}</pre>

              <pre v-if="issue.body">
                {{ issue.body }}
              </pre>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="notification is-info" v-else>No issues !</div>
  </div>
</template>

<style scoped>
tr.new_for_revision {
  background: #e6ffcc;
}

td.path {
  color: #4d4d4d;
  font-family: monospace;
}
</style>
