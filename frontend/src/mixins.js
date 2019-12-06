export default {
  query: {
    methods: {
      update_query (name, value) {
        console.log('update query', name, value)
        var query = Object.assign({}, this.$route.query)
        if (value !== null && value !== '') {
          query[name] = value
        } else if (name in query) {
          delete query[name]
        }
        if (this.$router) {
          this.$router.push({ 'query': query })
        }
      }
    }
  },
  stats: {
    computed: {
      stats () {
        return this.$store.state.stats
      },
      progress () {
        if (!this.$store.state.total_stats) {
          return 0
        }
        return 100 * this.stats.length / this.$store.state.total_stats
      }
    }
  },
  date: {
    filters: {
      // Display time since elapsed in a human format
      since (datetime) {
        var dspStep = (t, name) => {
          let x = Math.round(t)
          if (x === 0) {
            return ''
          }
          return x + ' ' + name + (x > 1 ? 's' : '')
        }

        let diff = (new Date() - new Date(datetime)) / 1000
        let steps = [
          [60, 'second'],
          [60, 'minute'],
          [24, 'hour'],
          [30, 'day'],
          [12, 'month']
        ]
        var prev = ''
        for (let [t, name] of steps) {
          if (diff > t) {
            prev = dspStep(diff % t, name)
            diff = diff / t
          } else {
            return dspStep(diff, name) + ' ' + prev
          }
        }
        return 'Too long ago'
      }
    }
  }
}
