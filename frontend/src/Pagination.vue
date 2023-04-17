<script>
export default {
  props: {
    api_data: Object,
    store_method: String,
    name: String,
  },
  data: function () {
    return {};
  },
  methods: {
    load_next_page() {
      if (!this.has_next) {
        return;
      }

      this.$store.dispatch(this.store_method, {
        url: this.api_data.next,
      });
    },
    load_previous_page() {
      if (!this.has_previous) {
        return;
      }

      this.$store.dispatch(this.store_method, {
        url: this.api_data.previous,
      });
    },
  },
  computed: {
    total() {
      return this.api_data.count;
    },
    page_nb() {
      return this.api_data.results.length;
    },
    has_next() {
      return this.api_data.next !== null;
    },
    has_previous() {
      return this.api_data.previous !== null;
    },
  },
};
</script>

<template>
  <nav class="columns" v-if="total > 0">
    <div class="column">
      <button
        class="button is-pulled-right is-dark"
        :disabled="!has_next"
        v-on:click="load_next_page"
      >
        Older {{ name }}↣
      </button>
      <button
        class="button is-pulled-right is-dark"
        :disabled="!has_previous"
        v-on:click="load_previous_page"
      >
        ↞ Newer {{ name }}
      </button>
      <div class="is-text-dark is-pulled-right">
        Showing {{ page_nb }}/{{ total }} {{ name }}
      </div>
    </div>
  </nav>
</template>

<style scoped>
nav.columns {
  margin-top: 12px;
}

nav.columns * {
  margin-left: 10px;
}

nav.columns div {
  padding-top: 5px;
}
</style>
