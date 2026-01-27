<script>
export default {
  props: {
    diffs: {
      type: Array,
      required: true,
    },
    maxInlined: {
      type: Number,
      default: 4,
    },
  },
  computed: {
    groupedDiffs() {
      /*
       * Group diffs by revision
       * [{revision: <rev>, msg: "<diff1>, <diff2>, …", count:5, remaining:3}, …]
       */
      const revObject = this.diffs.reduce((obj, diff) => {
        if (obj[diff.revision.id] === undefined) {
          obj[diff.revision.id] = {
            revision: diff.revision,
            msg: "",
            count: 0,
            remaining: 0,
          };
        }
        const rev = obj[diff.revision.id];
        rev.count += 1;
        if (rev.count === 1) {
          rev.msg = diff.id;
        } else if (rev.count > this.maxInlined) {
          rev.remaining += 1;
        } else {
          rev.msg = `${rev.msg}, ${diff.id}`;
        }
        if (rev.count === this.maxInlined + 1) rev.msg = `${rev.msg}…`;
        return obj;
      }, {});
      return Object.values(revObject);
    },
  },
};
</script>

<template>
  <div>
    <p v-for="group in groupedDiffs" class="is-nowrap">
      <a
        v-id="group.revision.provider == 'phabricator'"
        :href="group.revision.url"
        target="_blank"
        >D{{ group.revision.provider_id }}</a
      >
      <a
        v-id="group.revision.provider == 'github'"
        :href="group.revision.url"
        target="_blank"
        >PR n°{{ group.revision.provider_id }}</a
      >
      ({{ group.msg
      }}<template v-if="group.remaining >= 1"> +{{ group.remaining }}</template
      >)
    </p>
  </div>
</template>
