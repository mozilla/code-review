export default {
  stats: {
    computed: {
      stats () {
        return this.$store.state.stats
      },
      progress () {
        if (!this.stats.ids || !this.stats.loaded) {
          return 0.0
        }
        return 100 * this.stats.loaded / this.stats.ids.length
      }
    }
  },
  date: {
    filters: {
      // Display time since elapsed in a human format
      since (datetime) {
        var dspStep = (t, name) => (Math.round(t) + ' ' + name + (Math.round(t) > 1 ? 's' : ''))

        let diff = (new Date() - new Date(datetime)) / 1000
        let steps = [
          [60, 'second'],
          [60, 'minute'],
          [24, 'hour'],
          [30, 'day']
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
