<script>
import mixins from './mixins.js'

export default {
  mounted () {
    this.$store.dispatch('load_all_indexes')
  },
  mixins: [
    mixins.date
  ],
  computed: {
    tasks () {
      return this.$store.state.tasks
    }
  }
}
</script>

<template>
  <table class="table is-fullwidth">
    <thead>
      <tr>
        <td>#</td>
        <td>Revision</td>
        <td>State</td>
        <td>Nb. Issues</td>
        <td>Indexed</td>
        <td>Actions</td>
      </tr>
    </thead>

    <tbody>
      <tr v-for="task in tasks">
        <td>
          <a class="mono" :href="'https://tools.taskcluster.net/task-inspector/#' + task.taskId" target="_blank">{{ task.taskId }}</a>
        </td>

        <td v-if="task.data.source == 'mozreview'">

          <span class="tag is-success">MozReview</span> #{{ task.data.review_request }}

          <br />
          <small class="mono has-dark-text">{{ task.data.rev}}</small>
        </td>
        <td v-else-if="task.data.source == 'phabricator'">

          <span class="tag is-dark">Phabricator</span> #{{ task.data.id }}

          <br />
          <small class="mono has-dark-text">{{ task.data.diff_phid}}</small>
        </td>
        <td v-else>
          <p class="notification is-danger">Unknown data source: {{ task.data.source }}</p>
        </td>

        <td>
          <span class="tag is-light" v-if="task.data.state == 'started'">Started</span>
          <span class="tag is-info" v-else-if="task.data.state == 'cloned'">Cloned</span>
          <span class="tag is-info" v-else-if="task.data.state == 'analyzing'">Analyzing</span>
          <span class="tag is-primary" v-else-if="task.data.state == 'analyzed'">Analyzed</span>
          <span class="tag is-danger" v-else-if="task.data.state == 'error'">Error</span>
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
          <a class="button is-link" :href="task.data.url" target="_blank">Review</a>
          <router-link :to="{ name: 'task', params: { taskId : task.taskId }}" class="button is-primary">Details</router-link>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style>
a.mono{
  font-family: monospace;
}
</style>
