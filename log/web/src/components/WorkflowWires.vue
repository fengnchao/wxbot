<script setup>
// 两节点之间的连接带：静态路径 + 新事件到达时的 packet 动画。
defineProps({
  band: { type: String, required: true },
  paths: { type: Array, default: () => [] },
  traced: { type: Object, default: () => new Set() },
  color: { type: String, default: '#5d978e' }
})
</script>

<template>
  <div class="wf-wire-band" :class="'wf-band-' + band">
    <svg viewBox="0 0 1000 72" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <marker
          :id="'wf-arrow-' + band"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
        </marker>
      </defs>
      <g
        v-for="path in paths"
        :id="'wf-edge-' + path[0]"
        :key="path[0]"
        class="wf-wire"
        :class="{ traced: traced.has(path[0]) }"
        :style="{ '--trace-color': color }"
      >
        <path class="wf-wire-line" :d="path[1]" :marker-end="'url(#wf-arrow-' + band + ')'" />
        <path class="wf-packet" :d="path[1]" pathLength="100" />
      </g>
    </svg>
    <span
      v-for="(path, index) in paths"
      :key="'label-' + path[0]"
      class="wf-wire-label"
      :class="index ? 'right' : 'left'"
    >{{ path[2] }}</span>
  </div>
</template>
