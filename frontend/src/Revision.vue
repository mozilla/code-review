<script>
export default {
  mounted() {
    this.$store
      .dispatch("load_revision", { id: this.$route.params.revisionId })
      .then((resp) => {
        this.$set(this, "state", "loaded");
      })
      .catch((err) => {
        this.$set(this, "state", err);
      });
  },
  data() {
    return {
      state: "loading",
    };
  },
  computed: {
    revision() {
      return this.$store.state.revision;
    },
    paths() {
      // Load all issues
      const paths = new Set();
      for (const diff of this.revision.diffs) {
        const issues = this.$store.state.issues[diff.id] || [];
        for (const issue of issues) {
          paths.add(issue.path);
        }
      }

      return [...paths].sort();
    },
  },
  methods: {
    path_issues(diffId, path) {
      const issues = this.$store.state.issues[diffId] || [];
      return issues.filter((issue) => issue.path === path);
    },
  },
};
</script>

<template>
  <section>
    <div class="notification is-info" v-if="state == 'loading'">Loading...</div>
    <div v-else-if="state == 'loaded'">
      <h1 v-if="revision.provider == 'phabricator'" class="title">
        Revision D{{ revision.provider_id }}
      </h1>
      <h1 v-if="revision.provider == 'github'" class="title">
        Pull request {{ revision.provider_id }}
      </h1>

      <h2 class="subtitle">{{ revision.title }}</h2>
      <p>
        On <strong>{{ revision.head_repository }}</strong> -
        <a
          v-if="revision.provider == 'phabricator'"
          :href="revision.url"
          target="_blank"
          >View on Phabricator</a
        >
        <a
          v-if="revision.provider == 'github'"
          :href="revision.url"
          target="_blank"
          >View on Github</a
        >
        <span v-if="revision.bugzilla_id">
          -
          <a :href="'https://bugzil.la/' + revision.bugzilla_id" target="_blank"
            >View Bug {{ revision.bugzilla_id }}</a
          >
        </span>
      </p>

      <nav class="panel" v-for="path in paths">
        <p class="panel-heading">
          {{ path }}
        </p>
        <div class="panel-block">
          <div class="columns">
            <div class="column" v-for="diff in revision.diffs">
              <p>
                <router-link :to="{ name: 'diff', params: { diffId: diff.id } }"
                  >Diff {{ diff.id }}</router-link
                >
              </p>

              <table class="table">
                <tr>
                  <th>New</th>
                  <th>Line</th>
                  <th>Char</th>
                  <th>Analyzer</th>
                  <th>Check</th>
                  <th>Hash</th>
                </tr>
                <tr
                  v-for="issue in path_issues(diff.id, path)"
                  :class="{ new_for_revision: issue.new_for_revision }"
                >
                  <td>
                    <span v-if="issue.new_for_revision">✔</span>
                    <span v-else>❌</span>
                  </td>
                  <td>{{ issue.line }}</td>
                  <td>{{ issue.char }}</td>
                  <td>{{ issue.analyzer }}</td>
                  <td>{{ issue.check }}</td>
                  <td>
                    <samp>{{ issue.hash.substring(0, 8) }}</samp>
                  </td>
                </tr>
              </table>
            </div>
          </div>
        </div>
      </nav>
    </div>
    <div class="notification is-danger" v-else>
      <h4 class="title">Error</h4>
      {{ state }}
    </div>
  </section>
</template>

<style>
tr.new_for_revision {
  background: #e6ffcc;
}
</style>
