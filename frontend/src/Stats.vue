<script>
import mixins from './mixins.js'
import Progress from './Progress.vue'

export default {
  mixins: [
    mixins.stats,
    mixins.date
  ],
  data () {
    return {
      sort: 'detected'
    }
  },
  components: { Progress },
  mounted () {
    this.$store.dispatch('load_stats')
  },
  computed: {
    checks () {
      if (!this.stats) {
        return null
      }
      let sortStr = (x, y) => x.toLowerCase().localeCompare(y.toLowerCase())
      var sorts = {
        'repository': (x, y) => sortStr(x.repository, y.repository),
        'analyzer': (x, y) => sortStr(x.analyzer, y.analyzer) || sortStr(x.check, y.check),
        'check': (x, y) => sortStr(x.check, y.check),
        'detected': (x, y) => y.total - x.total,
        'published': (x, y) => y.publishable - x.publishable
      }

      // Apply local sort to the stats from store
      this.stats.sort(sorts[this.sort])
      return this.stats
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
    <Progress name="Statistics" />

    <div v-if="stats">
      <table class="table is-fullwidth" v-if="checks">
        <thead>
          <tr>
            <th>
              <span class="button" v-on:click="select_sort('repository')" :class="{'is-focused': sort == 'repository' }">Repository</span>
            </th>
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
            <td>{{ check.repository }}</td>
            <td>{{ check.analyzer }}</td>
            <td>{{ check.check }}</td>
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
