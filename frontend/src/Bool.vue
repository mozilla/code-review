<script>
export default {
  name: 'Bool',
  props: ['value', 'name']
}
</script>

<template>
  <span>
    <span v-if="value" class="has-text-success">&#x2714; {{ name }}</span>
    <span v-else class="has-text-danger">&#x2715; {{ name }}</span>
  </span>
</template>
