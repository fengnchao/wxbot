<script setup>
import { computed } from 'vue'
import {
  WF_STATUS, colorOf, deadlineText, statusLabel, workflowErrorSummary, workflowExcerpt
} from '../flow'

const props = defineProps({
  serviceId: { type: String, required: true },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  icon: { type: String, default: '' },
  messages: { type: Array, default: () => [] },
  cap: { type: Number, default: 8 },
  expanded: { type: Boolean, default: false },
  selectedId: { type: String, default: '' },
  trail: { type: Boolean, default: false },
  current: { type: Boolean, default: false },
  stream: { type: Object, default: null },
  streamContact: { type: String, default: '' },
  serverNow: { type: Number, default: 0 }
})

defineEmits(['select', 'more'])

const shown = computed(() => (props.expanded ? props.messages : props.messages.slice(0, props.cap)))
const hidden = computed(() => Math.max(0, props.messages.length - props.cap))

const EMPTY_TEXT = {
  model: '等待新的模型请求',
  inbox: '暂无待合并或待提交消息',
  outbox: '暂无等待发送的回复',
  butler: '接收、调度与回复共用此节点'
}
const emptyText = computed(() => EMPTY_TEXT[props.serviceId] || '接收消息 · 输入回复 · 确认发送')

const FALLBACK_NOTES = {
  final_composition: '此请求需要完成回复整理后再发送，处理进度仍实时显示。',
  group_identity: '群提及身份需在最终结果核验，本轮等待完整回复。',
  complete_only: '此后端等待完整回复后发送。'
}
const fallbackNote = computed(() => FALLBACK_NOTES[props.stream?.model?.fallback] || '本轮等待完整回复后发送。')

function textOf(message) {
  return message.stage >= 5 && message.reply_preview ? message.reply_preview : message.preview
}

/** 未结束的任务按阶段说明进度，结束或有异常时以队列状态为准。 */
function rowStatus(message) {
  if (message.scope === 'issues' || message.terminal) return WF_STATUS[message.status] || message.status
  return ({ 2: '接收 / 调度', 4: '完整结果就绪', 9: '新闻投递' }[message.stage]) ||
    WF_STATUS[message.status] || message.status
}

function lastTool(message) {
  const events = message.events || []
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].stage === 'hermes_tool') return events[index]
  }
  return null
}

function modelProgress(message) {
  const tool = lastTool(message)
  const text = tool
    ? '工具 ' + (tool.tool || '未知') + ' · ' + statusLabel(tool.status)
    : '等待模型过程事件'
  return text + ' · 请求 ' + ((message.request_id || '').slice(0, 10) || message.id)
}
</script>

<template>
  <div
    :id="'wf-node-' + serviceId"
    :data-service="serviceId"
    class="wf-node"
    :class="['wf-service-' + serviceId, { traced: trail, current }]"
  >
    <div class="wf-node-label">
      <span class="wf-service-icon">{{ icon }}</span>
      <div>
        <h3>{{ title }}</h3>
        <p>{{ subtitle }}</p>
      </div>
      <span class="wf-service-count">{{ messages.length }} <small>{{ serviceId === 'model' ? '条请求' : '条' }}</small></span>
    </div>
    <div class="wf-node-messages">
      <button
        v-for="message in shown"
        :key="message.id"
        class="wf-summary-row"
        :class="{ selected: selectedId === message.id, issue: message.scope === 'issues' }"
        :data-wf-select="message.id"
        :data-focus-key="'wf-node-' + message.id"
        :style="{ '--identity': colorOf(message) }"
        :aria-label="'查看 ' + message.contact + ' 消息 ' + message.id"
        @click="$emit('select', message.id)"
      >
        <span class="wf-row-text">
          <strong>{{ message.contact }}</strong>
          <span class="wf-row-content"> · {{ workflowExcerpt(textOf(message)) }}</span>
        </span>
        <span class="wf-row-sub">
          <span class="wf-row-uid">
            UID {{ message.uid }}{{ message.group ? ' / 成员 ' + ((message.members || []).join(', ') || '未记录') : '' }}
          </span>
          <span>{{ rowStatus(message) }}{{ message.part_count ? ' · ' + message.sent_parts + '/' + message.part_count + ' 句' : '' }}</span>
        </span>
        <span v-if="serviceId === 'model'" class="wf-model-progress">{{ modelProgress(message) }}</span>
        <span v-if="message.error" class="wf-row-error">{{ workflowErrorSummary(message) }}</span>
        <span v-if="message.scope === 'issues'" class="wf-recovery">
          <span v-if="message.attempts">已尝试 {{ message.attempts }} 次 · 重试 {{ Math.max(0, message.attempts - 1) }} 次</span>
          <span v-if="message.retry_at">自动重试：<b>{{ deadlineText(message.retry_at, serverNow) }}</b></span>
          <span v-if="message.discard_at && !message.terminal">失败到期释放：<b>{{ deadlineText(message.discard_at, serverNow) }}</b></span>
        </span>
      </button>
      <div v-if="!shown.length" class="wf-service-empty">{{ emptyText }}</div>
    </div>
    <template v-if="serviceId === 'model'">
      <div v-if="!stream?.id" class="wf-stream-empty">正在处理的请求会实时显示在这里；也可点选消息查看已记录的模型输出。</div>
      <div v-else class="wf-stream">
        <div class="wf-stream-heading">
          <b>{{ streamContact || '当前请求' }}</b>
          <span>{{ stream.error || stream.status || '正在读取模型进度' }}</span>
        </div>
        <p v-if="stream.model?.fallback" class="wf-note">{{ fallbackNote }}</p>
        <div class="wf-stream-columns">
          <div>
            <h4>思考摘要</h4>
            <pre>{{ stream.summary || '后端尚未提供公开摘要' }}</pre>
            <h4>工具进度</h4>
            <ul v-if="stream.tools?.length">
              <li v-for="(tool, index) in stream.tools" :key="'tool-' + index">{{ tool.tool || '工具' }} · {{ tool.status || '处理中' }}</li>
            </ul>
            <p v-else class="wf-note">暂无工具事件</p>
          </div>
          <div>
            <h4>回复正文</h4>
            <pre>{{ stream.answer || '等待最终回答正文…' }}</pre>
          </div>
        </div>
      </div>
    </template>
    <button v-if="hidden" class="wf-more" :data-wf-more="serviceId" @click="$emit('more', serviceId)">
      {{ expanded ? '收起' : '查看其余 ' + hidden + ' 条' }}
    </button>
  </div>
</template>
