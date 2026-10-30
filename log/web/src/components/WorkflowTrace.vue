<script setup>
import { computed } from 'vue'
import { fullTime } from '../api'
import {
  WF_DECISIONS, WF_IDENTITIES, WF_MENTIONS, WF_STATUS, colorOf, deadlineText, groupFlowEvents,
  hm, p2, stageLabel, statusLabel, workflowErrorSummary
} from '../flow'

const props = defineProps({
  message: { type: Object, required: true },
  content: { type: Object, default: null },
  serverNow: { type: Number, default: 0 }
})

defineEmits(['deselect', 'diagnose'])

const BAD_STATUS = ['error', 'failed', 'blocked', 'uncertain', 'skipped', 'media_failed']

const events = computed(() => groupFlowEvents(props.message.events || []))
// 选中消息变化后旧全文不再复用，避免把上一条正文显示在新记录下。
const body = computed(() => (props.content?.id === props.message.id ? props.content : null))

const metadata = computed(() => {
  const message = props.message
  const rows = []
  if (message.user_id) rows.push(['固定用户 ID', message.user_id])
  if (message.binding_id) rows.push(['通道绑定 ID', message.binding_id])
  if (message.identity_status) rows.push(['身份', WF_IDENTITIES[message.identity_status] || message.identity_status])
  if (Number.isInteger(message.memory_count)) rows.push(['召回记忆', message.memory_count + ' 条'])
  if (Number.isInteger(message.context_count)) {
    rows.push(['群公共上下文', message.context_count + ' 条 · 序号 ' +
      (message.context_from ?? 0) + '–' + (message.context_to ?? 0)])
  }
  if (message.decision) rows.push(['回复决策', WF_DECISIONS[message.decision] || message.decision])
  if (message.mention_stage) rows.push(['微信提及', WF_MENTIONS[message.mention_stage] || message.mention_stage])
  return rows
})

function traceTime(event) {
  if (event.time_unknown) return '时间未记录'
  return hm(event.ts) + ':' + p2(new Date(event.ts * 1000).getSeconds())
}
</script>

<template>
  <div class="wf-inspect" :style="{ '--identity': colorOf(message) }">
    <div class="row">
      <b>{{ message.contact }} · 流转详情</b>
      <button id="wf-deselect" aria-label="取消消息选择" @click="$emit('deselect')">×</button>
    </div>
    <template v-if="!(message.uid === message.contact && !message.group)">
      <span class="wf-identity">UID <code>{{ message.uid }}</code><b v-if="message.group">群聊</b></span>
    </template>
    <span v-if="message.group" class="wf-member">
      成员 {{ (message.members || []).length ? (message.members || []).join(' / ') : '未记录' }}
    </span>
    <div v-if="metadata.length" class="wf-meta">
      <div v-for="row in metadata" :key="row[0]"><strong>{{ row[0] }}</strong> · <span>{{ row[1] }}</span></div>
    </div>
    <div class="wf-meta">{{ fullTime(message.at) }} · 当前：{{ WF_STATUS[message.status] || message.status }}</div>

    <template v-if="body?.status === 'ok'">
      <div class="wf-meta">{{ message.kind === 'push' ? '推送正文' : '消息正文' }}</div>
      <div class="wf-fulltext">{{ body.text || '此消息没有文字正文' }}</div>
      <template v-if="body.reply_text">
        <div class="wf-meta">回复正文</div>
        <div class="wf-fulltext">{{ body.reply_text }}</div>
      </template>
    </template>
    <p v-else :class="body?.status === 'error' ? 'wf-error' : 'wf-note'">
      {{ body?.error || '正在读取消息全文…' }}
    </p>

    <p v-if="message.error" class="wf-error">{{ workflowErrorSummary(message) }}</p>
    <div class="wf-recovery">
      <span v-if="message.attempts">已尝试 {{ message.attempts }} 次 · 重试 {{ Math.max(0, message.attempts - 1) }} 次</span>
      <span v-if="message.retry_at">自动重试：<b>{{ deadlineText(message.retry_at, serverNow) }}</b></span>
      <span v-if="message.discard_at && !message.terminal">失败到期释放：<b>{{ deadlineText(message.discard_at, serverNow) }}</b></span>
    </div>
    <ol class="wf-trace">
      <li v-for="(event, index) in events" :key="event.stage + '-' + index" :class="{ bad: BAD_STATUS.includes(event.status) }">
        <time>{{ traceTime(event) }}</time>
        <div>
          <b>{{ stageLabel(event.stage) }}</b>
          <small>
            {{ statusLabel(event.status) }}<template v-if="!event.time_unknown && event.elapsed_ms != null"> · {{ (event.elapsed_ms / 1000).toFixed(2) }} 秒</template><template v-if="event.tool"> · {{ event.tool }}</template>
          </small>
        </div>
      </li>
    </ol>
    <p v-if="message.events_truncated" class="wf-note">此处保留最近 200 条事件。</p>
    <p class="wf-note">未记录的阶段保持未确认；动画只表示新事件到达。</p>
    <button id="wf-diagnose" @click="$emit('diagnose')">在收发队列中查看 / 处理</button>
  </div>
</template>
