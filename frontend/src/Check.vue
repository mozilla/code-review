<script>
import mixins from './mixins.js'

export default {
  mixins: [
    mixins.stats
  ],
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
    <h1 class="title">Check {{ check_name }}</h1>
    <h2 class="subtitle" v-if="stats && stats.ids">Loaded {{ stats.loaded }}/{{ stats.ids.length }} tasks</h2>

    <div v-if="stats">
      <progress class="progress is-info" :class="{'is-info': progress < 100, 'is-success': progress >= 100}" :value="progress" max="100">{{ progress }}%</progress>

      <table class="table is-fullwidth" v-if="check">
        <thead>
          <tr>
            <th>Task</th>
            <th>Review</th>
            <th>Path</th>
            <th>Line</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="issue in check.issues">
            <td>
              <a class="mono" :href="'https://tools.taskcluster.net/task-inspector/#' + issue.taskId" target="_blank">{{ issue.taskId }}</a>
            </td>
            <td>
              <a :href="issue.revision.url" target="_blank" v-if="issue.revision.source == 'phabricator'">Phabricator {{ issue.revision.id }}</a>
              <a :href="issue.revision.url" target="_blank" v-else-if="issue.revision.source == 'mozreview'">Mozreview {{ issue.revision.review_reques }}</a>
              <span v-else>Unknown</span>
            </td>
            <td class="mono">{{ issue.path }}</td>
            <td>{{ issue.line }}</td>
            <td>
              {{ issue.message }}
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
