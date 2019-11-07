<script>
import mixins from './mixins.js'
import Progress from './Progress.vue'

export default {
  mixins: [
    mixins.stats
  ],
  components: { Progress },
  mounted () {
    this.$store.dispatch('calc_stats')
  },
  computed: {
    check_name () {
      return this.$route.params.check
    },
    check () {
      if (!this.stats || !this.stats.loaded) {
        return null
      }
      // Shallow clone to trigger Vue js reactivity on deeply nested objects
      return Object.assign({}, this.$store.state.stats.checks[this.check_name])
    }
  }
}
</script>

<template>
  <div>
    <Progress :name="'Check ' + check_name" />

    <div v-if="stats">
      <table class="table is-fullwidth" v-if="check">
        <thead>
          <tr>
            <th>Task</th>
            <th>Review</th>
            <th>Bug</th>
            <th>Path</th>
            <th>Line</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="issue in check.issues">
            <td>
              <a class="mono" :href="'https://firefox-ci-tc.services.mozilla.com/tasks/' + issue.taskId" target="_blank">{{ issue.taskId }}</a>
            </td>
            <td>
              <a :href="issue.revision.url" target="_blank">D{{ issue.revision.id }}</a>
            </td>
            <td>
              <span v-if="issue.revision.bugzilla_id"><a :href="'https://bugzil.la/' + issue.revision.bugzilla_id" target="_blank">Bug {{ issue.revision.bugzilla_id }}</a></span>
              <span v-else>Unknown</span>
            </td>
            <td class="mono">{{ issue.path }}</td>
            <td>{{ issue.line }}</td>
            <td>
              <pre>{{ issue.message }}</pre>
            </td>
          </tr>
        </tbody>

      </table>
      <p v-else class="notification is-warning">No data available for this check</p>
    </div>
    <div class="notification is-info" v-else>Loading tasks...</div>
  </div>
</template>

<style>
.mono{
  font-family: monospace;
}
</style>
