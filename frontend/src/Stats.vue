<script>
import mixins from './mixins.js'

export default {
  mixins: [
    mixins.stats,
    mixins.date
  ],
  data () {
    return {
      sort: 'published'
    }
  },
  computed: {
    checks () {
      if (!this.stats || !this.stats.loaded) {
        return null
      }
      let sortStr = (x, y) => x.toLowerCase().localeCompare(y.toLowerCase())
      var sorts = {
        'analyzer': (x, y) => sortStr(x.analyzer, y.analyzer) || sortStr(x.check, y.check),
        'check': (x, y) => sortStr(x.check, y.check),
        'detected': (x, y) => y.total - x.total,
        'published': (x, y) => y.publishable - x.publishable
      }

      // Apply local sort to the checks from store
      var checks = Object.values(this.stats.checks)
      checks.sort(sorts[this.sort])
      return checks
    }
  },
  methods: {
    select_sort (name) {
      this.$set(this, 'sort', name)
    }
  }
}
</script>

<template>
  <div>
    <h1 class="title">Statistics</h1>
    <h2 class="subtitle" v-if="stats && stats.ids">
      <span>Loaded {{ stats.loaded }}/{{ stats.ids.length }} tasks with issues</span>
      <span v-if="stats && stats.start_date" :title="stats.start_date">, since {{ stats.start_date|since }} ago</span>
    </h2>

    <div v-if="stats">
      <progress class="progress is-info" :class="{'is-info': progress < 100, 'is-success': progress >= 100}" :value="progress" max="100">{{ progress }}%</progress>

      <table class="table is-fullwidth" v-if="checks">
        <thead>
          <tr>
            <th>
              <span class="button" v-on:click="select_sort('analyzer')" :class="{'is-focused': sort == 'analyzer' }">Analyzer</span>
            </th>
            <th>
              <span class="button" v-on:click="select_sort('check')" :class="{'is-focused': sort == 'check' }">Check</span>
            </th>
            <th>
              <span class="button" v-on:click="select_sort('detected')" :class="{'is-focused': sort == 'detected' }">Detected</span>
            </th>
            <th>
              <span class="button" v-on:click="select_sort('published')" :class="{'is-focused': sort == 'published' }">Published</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="check in checks" :class="{'publishable': check.publishable > 0}">
            <td>{{ check.analyzer }}</td>
            <td>
              {{ check.check }}
              <span class="has-text-grey" v-if="check.analyzer == 'mozlint.flake8'">{{ check.message }}</span>
            </td>
            <td>{{ check.total }}</td>
            <td>
              <router-link v-if="check.publishable > 0" :to="{ name: 'check', params: { check: check.key }}">{{ check.publishable }}</router-link>
              <span class="has-text-grey" v-else>0</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="notification is-info" v-else>Loading tasks...</div>

  </div>
</template>

<style scoped>
tr.publishable {
  background: #e6ffcc;
}
</style>
