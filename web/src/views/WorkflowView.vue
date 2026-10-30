<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { fullTime } from '../api'
import { go } from '../router'
import { focusQueue } from '../queueFocus'
import WorkflowNode from '../components/WorkflowNode.vue'
import WorkflowTrace from '../components/WorkflowTrace.vue'
import WorkflowWires from '../components/WorkflowWires.vue'
import {
  WF_STATUS, colorOf, hm, stageLabel, statusLabel, workflowErrorSummary, workflowEventEdge,
  workflowExcerpt, workflowService
} from '../flow'
import {
  content, data, deleting, error, expanded, lastSuccess, notice, overview, paused, selected, scope
} from '../workflowState'

const props = defineProps({ tab: { type: String, default: 'workflow' } })
const ctx = inject('logWebCtx', null)

const SCOPES = [['all', '最近消息'], ['active', '进行中'], ['issues', '异常记录'], ['complete', '已完成']]
const DIRECT_MODEL_PATHS = [
  ['dispatch', 'M240 72 V38 H420 V2', '↑ 请求模型'],
  ['enqueue', 'M580 0 V38 H760 V70', '↓ 回复入队']
]
const MODEL_PATHS = [
  ['request', 'M420 72 V2', '↑ 请求模型'],
  ['result', 'M580 0 V70', '↓ 完整回复']
]
const QUEUE_PATHS = [
  ['dispatch', 'M240 72 V38 H420 V2', '↑ 提交收件'],
  ['enqueue', 'M580 0 V38 H760 V70', '↓ 回复入队']
]
const WECHAT_PATHS = [
  ['receive', 'M420 72 V38 H240 V2', '↑ 收到消息'],
  ['send', 'M760 0 V38 H580 V70', '↓ 发送回复']
]

const nowMs = ref(Date.now())
const stream = reactive({
  id: '', cursor: 0, summary: '', answer: '', tools: [], model: null, status: '', error: ''
})

let alive = false
let epoch = 0
let busy = false
let baseline = false
let pollTimer = null
let pollController = null
let contentController = null
let streamEpoch = 0
let streamTimer = null
let streamController = null
let clockTimer = null
let pulseTimers = []

const query = computed(() => String(ctx?.search?.[props.tab] || '').trim().toLowerCase())

function matches(message) {
  const needle = query.value
  if (!needle) return true
  return [message.contact, message.uid, message.user_id, message.binding_id, message.label,
    (message.members || []).join(' '), message.request_id, message.id,
    (message.inbox_ids || []).join(' '), message.preview, message.reply_preview, message.error]
    .some(value => String(value ?? '').toLowerCase().includes(needle))
}

const visible = computed(() => (data.value?.messages || []).filter(matches))
const counts = computed(() => data.value?.counts || {})
const selectedMessage = computed(() =>
  (data.value?.messages || []).find(message => message.id === selected.value) || null)

function inScope(message, value = scope.value) {
  if (value === 'all') return true
  if (value === 'active') return !message.terminal && message.scope !== 'issues'
  return message.scope === value
}

const scopedMessages = computed(() => visible.value.filter(message => inScope(message))
  .sort((a, b) => (scope.value === 'active'
    ? a.at - b.at || a.id.localeCompare(b.id)
    : b.updated_at - a.updated_at || b.id.localeCompare(a.id))))

function countInScope(value) {
  return visible.value.filter(message => inScope(message, value)).length
}

const stats = computed(() => {
  const count = counts.value
  return [
    ['待处理轮次', count.active, '全部会话'],
    ['待合并收件', count.inbox, '全部会话'],
    ['等待模型', count.model, '已领取，等待完整结果'],
    ['待发送分句', count.outbox, '全部会话'],
    ['进行中异常', count.issues, '当前需要关注'],
    ['已结束异常', count.closed_issues, '全部会话']
  ].map(([label, value, note], index) => ({ label, value, note, attention: index === 4 && Boolean(value) }))
})

const liveText = computed(() => (error.value
  ? '数据已过期 · 自动重连'
  : lastSuccess.value ? '实时读取 · 1 秒' : '正在连接'))
const updatedText = computed(() => (lastSuccess.value
  ? '最近成功读取 ' + new Date(lastSuccess.value).toLocaleTimeString('zh-CN', { hour12: false })
  : '尚无成功读取'))

// 服务端时间 = 最近快照时间 + 成功读取后的本地经过时间；断线时冻结倒计时。
const serverNow = computed(() => (data.value?.at || 0) +
  (error.value ? 0 : Math.max(0, (nowMs.value - lastSuccess.value) / 1000)))

const warnSources = computed(() => (data.value?.sources || [])
  .filter(source => source.status !== 'ok' || source.truncated)
  .map(source => ({
    name: source.name,
    text: source.error || (source.status === 'missing' ? '数据尚未创建'
      : source.status !== 'ok' ? '数据暂不可读取'
        : source.name === 'Telegram' ? '仅载入部分消息，更多见收发队列' : '仅载入最近 4 MB 过程事件')
  })))
const sourceNote = computed(() => warnSources.value.map(item => item.name + '：' + item.text).join('；'))

const modelRoute = computed(() => (data.value?.model?.via_butler === false
  ? '微信 → 收件 → 模型 → 发件 → 微信'
  : '微信 → 收件 → Butler ⇄ 模型 → 发件 → 微信'))

function modelLabel(payload = data.value) {
  const info = stream.model || payload?.model
  return info
    ? String(info.label || info.provider || '模型') + (info.model ? ' · ' + info.model : '')
    : ({ hermes: 'Hermes', codex: 'Codex' }[payload?.backend] || '模型')
}

const streamContact = computed(() =>
  ((data.value?.messages || []).find(message => message.id === stream.id)?.contact) || '')

const recentIds = computed(() => new Set((data.value?.messages || [])
  .filter(message => message.terminal && data.value.at - message.updated_at < 15)
  .map(message => message.id)))

// 异常记录只通过右侧列表查看，避免长期占用流转概览。
const diagramMessages = computed(() => visible.value.filter(message =>
  message.id === selected.value || (message.scope !== 'issues' && (!message.terminal || recentIds.value.has(message.id)))))

function serviceMessages(serviceId) {
  return diagramMessages.value
    .filter(message => workflowService(message.stage) === serviceId)
    .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
}

const trailServices = computed(() => new Set((selectedMessage.value?.events || [])
  .map(event => workflowService(event.node))))
const tracedEdges = computed(() => new Set((selectedMessage.value?.events || []).map(workflowEventEdge)))
const traceColor = computed(() => (selectedMessage.value ? colorOf(selectedMessage.value) : '#5d978e'))

function nodeProps(serviceId, title, subtitle, icon, cap) {
  return {
    serviceId,
    title,
    subtitle,
    icon,
    cap,
    messages: serviceMessages(serviceId),
    expanded: expanded.has(serviceId),
    selectedId: selected.value,
    trail: trailServices.value.has(serviceId),
    current: Boolean(selectedMessage.value && workflowService(selectedMessage.value.stage) === serviceId),
    stream,
    streamContact: streamContact.value,
    serverNow: serverNow.value
  }
}

const recentEvents = computed(() => visible.value
  .flatMap(message => message.events.map(event => ({ m: message, e: event })))
  .sort((a, b) => b.e.ts - a.e.ts)
  .slice(0, 6))

function textOf(message) {
  return message.stage >= 5 && message.reply_preview ? message.reply_preview : message.preview
}

function identityVisible(message) {
  return !(message.uid === message.contact && !message.group)
}

function freshEvents(previous, next, isBaseline) {
  if (!previous || !isBaseline) return []
  const seen = new Set(previous.messages.flatMap(message => message.events.map(event => event.key)))
  // 旧历史的迟到快照不算新传输，只有上次快照之后产生的事件才播动画。
  const fresh = next.messages.flatMap(message => message.events
    .filter(event => !seen.has(event.key) && event.ts >= previous.at)
    .map(event => ({ m: message, e: event })))
  for (const message of next.messages) {
    const prior = previous.messages.find(item => item.id === message.id)
    if (prior && (prior.stage !== message.stage || prior.status !== message.status ||
      prior.delivery_id !== message.delivery_id) &&
      !fresh.some(item => item.m.id === message.id && item.e.node === message.stage)) {
      let evidence = null
      for (let index = message.events.length - 1; index >= 0; index -= 1) {
        if (message.events[index].node === message.stage) { evidence = message.events[index]; break }
      }
      if (evidence) fresh.push({ m: message, e: evidence })
    }
  }
  return fresh
}

function stopPulses() {
  pulseTimers.forEach(clearTimeout)
  pulseTimers = []
  document.querySelectorAll('.wf-pulse').forEach(node => node.classList.remove('wf-pulse'))
}

function pulse(events) {
  if (paused.value || error.value || !events.length) return
  const targets = new Map()
  for (const { m, e } of events) {
    targets.set('wf-node-' + workflowService(e.node), colorOf(m))
    const edge = workflowEventEdge(e)
    if (edge) targets.set('wf-edge-' + edge, colorOf(m))
  }
  for (const [id, color] of targets) {
    const node = document.getElementById(id)
    if (!node) continue
    node.style.setProperty('--packet-color', color)
    node.classList.remove('wf-pulse')
    void node.offsetWidth
    node.classList.add('wf-pulse')
    pulseTimers.push(setTimeout(() => node.classList.remove('wf-pulse'), 950))
  }
  // 长时间监控时限制待清理的定时器数量。
  if (pulseTimers.length > 40) pulseTimers.splice(0, pulseTimers.length - 40).forEach(clearTimeout)
}

function stopStream() {
  streamEpoch += 1
  clearTimeout(streamTimer)
  streamTimer = null
  streamController?.abort()
  streamController = null
  Object.assign(stream, {
    id: '', cursor: 0, summary: '', answer: '', tools: [], model: null, status: '', error: ''
  })
}

async function loadStream() {
  if (!alive || !overview.value || deleting.value || document.hidden) { stopStream(); return }
  const messages = data.value?.messages || []
  const target = messages.find(message => message.id === selected.value && message.kind === 'batch') ||
    (!selected.value && messages.find(message => message.kind === 'batch' && !message.terminal))
  if (!target) { stopStream(); return }
  if (stream.id !== target.id) { stopStream(); stream.id = target.id }
  if (streamController) return
  clearTimeout(streamTimer)
  const mine = streamEpoch
  const id = target.id
  const controller = new AbortController()
  streamController = controller
  const timeout = setTimeout(() => controller.abort(), 5000)
  const current = () => alive && overview.value && mine === streamEpoch && id === stream.id &&
    streamController === controller
  let more = false
  try {
    const response = await fetch('/api/workflow-stream?' + new URLSearchParams({ id, after: String(stream.cursor) }),
      { signal: controller.signal, cache: 'no-store' })
    const payload = await response.json()
    if (!current()) return
    if (!response.ok || payload.id !== id) throw new Error(payload.error || '模型实时输出暂不可读取')
    if (payload.reset) Object.assign(stream, { summary: '', answer: '', tools: [], model: null })
    for (const event of payload.events || []) {
      if (event.type === 'summary_delta') stream.summary = (stream.summary + String(event.text || '')).slice(-16000)
      if (event.type === 'answer_delta') stream.answer = (stream.answer + String(event.text || '')).slice(-32000)
      if (event.type === 'tool') stream.tools = [...stream.tools, event].slice(-8)
      if (event.type === 'backend') {
        stream.model = {
          ...data.value?.model, ...event,
          label: ({ codex: 'Codex', hermes: 'Hermes', deepseek: 'DeepSeek', openclaw: 'OpenClaw', cursor: 'Cursor' }[event.provider] ||
            data.value?.model?.label || event.provider)
        }
      }
      if (event.type === 'complete') stream.status = '模型已完成'
      if (event.type === 'error') stream.status = '本轮已中止'
    }
    stream.cursor = Number(payload.cursor) || 0
    stream.error = ''
    more = Boolean(payload.more)
    if (!stream.status) {
      stream.status = payload.available ? (target.terminal ? '历史模型记录' : '生成中') : '此记录暂无模型实时输出'
    }
  } catch (err) {
    if (current()) {
      stream.error = err.name === 'AbortError' ? '读取超时，正在重连' : '模型实时输出暂不可读取'
    }
  } finally {
    clearTimeout(timeout)
    if (current()) {
      streamController = null
      if (!target.terminal || more) streamTimer = setTimeout(loadStream, 400)
    }
  }
}

async function loadContent(message) {
  if (!message || selected.value !== message.id) return
  const version = JSON.stringify([message.id, message.preview, message.part_count])
  if (content.value?.version === version && ['loading', 'ok'].includes(content.value.status)) return
  contentController?.abort()
  const mine = epoch
  const controller = new AbortController()
  contentController = controller
  content.value = { id: message.id, version, status: 'loading' }
  const timeout = setTimeout(() => controller.abort(), 5000)
  const current = () => mine === epoch && alive && selected.value === message.id && contentController === controller
  try {
    const response = await fetch('/api/workflow-content?' + new URLSearchParams({ id: message.id }),
      { signal: controller.signal, cache: 'no-store' })
    const payload = await response.json()
    if (!current()) return
    if (!response.ok) {
      throw new Error(payload.status === 'missing' ? payload.error
        : response.status === 404 ? '消息全文接口尚未加载，请手动重启 log 服务后刷新页面'
          : payload.error || '消息全文暂时不可读取')
    }
    if (payload.status !== 'ok' || payload.id !== message.id) throw new Error('消息全文返回结果不匹配，请重试')
    content.value = {
      id: message.id, version, status: 'ok',
      text: String(payload.text ?? ''), reply_text: String(payload.reply_text ?? '')
    }
  } catch (err) {
    if (!current()) return
    content.value = {
      id: message.id, version, status: 'error',
      error: err.name === 'AbortError' ? '消息全文读取超时，请重试'
        : err instanceof TypeError ? '无法连接 log 服务' : err.message
    }
  } finally {
    clearTimeout(timeout)
    if (current()) contentController = null
  }
}

async function loadWorkflow() {
  if (!alive || busy || deleting.value) return
  clearTimeout(pollTimer)
  pollTimer = null
  if (document.hidden) {
    baseline = false
    stopPulses()
    pollTimer = setTimeout(loadWorkflow, 1000)
    return
  }
  const mine = epoch
  const controller = new AbortController()
  pollController = controller
  busy = true
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch('/api/workflow', { signal: controller.signal, cache: 'no-store' })
    if (!response.ok) {
      throw new Error(response.status === 404
        ? '工作流接口尚未加载，请手动重启 log 服务后刷新页面'
        : '读取失败（HTTP ' + response.status + '）')
    }
    const payload = await response.json()
    if (mine !== epoch || !alive) return
    if (payload.status !== 'ok') throw new Error(payload.error || '队列尚不可读取')
    const fresh = freshEvents(data.value, payload, baseline)
    const oldSelected = data.value?.messages.find(message => message.id === selected.value)
    if (oldSelected && !payload.messages.some(message => message.id === selected.value)) {
      selected.value = payload.messages
        .find(message => message.inbox_ids.some(id => oldSelected.inbox_ids.includes(id)))?.id || ''
    }
    data.value = payload
    error.value = ''
    lastSuccess.value = Date.now()
    baseline = true
    const chosen = payload.messages.find(message => message.id === selected.value)
    if (chosen) loadContent(chosen)
    else {
      contentController?.abort()
      contentController = null
      content.value = null
    }
    if (overview.value) loadStream()
    if (!paused.value) {
      await nextTick()
      if (alive) pulse(fresh)
    }
    ctx?.markRefreshed?.()
  } catch (err) {
    if (mine !== epoch || !alive) return
    error.value = err.name === 'AbortError' ? '读取超时，正在重连'
      : err instanceof TypeError ? '无法连接 log 服务' : err.message
    baseline = false
    stopPulses()
  } finally {
    clearTimeout(timeout)
    if (mine === epoch && alive) {
      busy = false
      pollController = null
      pollTimer = setTimeout(loadWorkflow, 1000)
    }
  }
}

async function deleteWorkflow(action, id = '') {
  if (deleting.value) return
  const message = data.value?.messages.find(item => item.id === id)
  if (action === 'single' && message?.can_delete !== true) return
  if (action === 'failed' && !(data.value?.counts?.closed_issues > 0)) return
  const question = action === 'failed'
    ? '永久移除全部已结束的微信异常记录？这会清理所有历史异常，不仅是当前搜索结果。进行中任务不受影响，原始队列审计仍保留，不会重发消息。'
    : '永久从工作流历史移除此记录？原始队列审计仍保留，不会重发消息。'
  if (typeof window !== 'undefined' && typeof window.confirm === 'function' && !window.confirm(question)) return
  deleting.value = true
  notice.value = '正在移除…'
  const mine = ++epoch
  clearTimeout(pollTimer)
  pollTimer = null
  pollController?.abort()
  pollController = null
  busy = false
  contentController?.abort()
  contentController = null
  stopStream()
  // 被中止的全文读取不能继续缓存为读取中。
  if (content.value?.status === 'loading') content.value = null
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const body = { action, acknowledge: true }
    if (action === 'single') { body.id = id; body.version = message.delete_version }
    const response = await fetch('/api/workflow-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Wxbot-Workflow-Action': '1' },
      body: JSON.stringify(body),
      signal: controller.signal
    })
    const result = await response.json()
    if (mine !== epoch) return
    if (!response.ok || !result.ok) throw new Error(result.error || '记录状态已变化，请刷新后重试')
    // 先本地移除再轮询；旧的进行中快照属于不同 epoch，不会把它加回来。
    if (data.value) {
      data.value.messages = data.value.messages.filter(item => (action === 'single'
        ? item.id !== id
        : !(item.can_delete === true && item.terminal && item.scope === 'issues')))
    }
    if (!data.value?.messages.some(item => item.id === selected.value)) {
      selected.value = ''
      content.value = null
    }
    notice.value = '已移除 ' + (Number(result.removed) || 0) + ' 条历史记录'
  } catch (err) {
    if (mine === epoch) {
      notice.value = err.name === 'AbortError' ? '移除请求超时，请刷新核实结果'
        : err instanceof TypeError ? '无法连接 log 服务，移除未确认' : err.message
    }
  } finally {
    clearTimeout(timeout)
    deleting.value = false
    if (mine !== epoch) notice.value = ''
    if (alive) loadWorkflow()
  }
}

function selectMessage(id) {
  selected.value = id
  if (overview.value) loadStream()
  loadContent(selectedMessage.value)
}

function deselect() {
  selected.value = ''
  contentController?.abort()
  contentController = null
  content.value = null
  stopStream()
  if (overview.value) loadStream()
}

function toggleOverview() {
  overview.value = !overview.value
  if (overview.value) loadStream()
  else stopStream()
}

function toggleAnimation() {
  paused.value = !paused.value
  stopPulses()
}

function toggleMore(serviceId) {
  if (expanded.has(serviceId)) expanded.delete(serviceId)
  else expanded.add(serviceId)
}

function diagnose() {
  const message = selectedMessage.value
  if (!message) return
  focusQueue({
    contact: message.contact || '',
    state: 'all',
    scope: message.terminal ? 'history' : message.scope === 'issues' ? 'issues' : 'active'
  })
  go('queue')
}

function onVisibility() {
  if (document.hidden) {
    baseline = false
    stopPulses()
  } else if (alive) {
    loadWorkflow()
  }
}

function stopAll() {
  epoch += 1
  clearTimeout(pollTimer)
  pollTimer = null
  pollController?.abort()
  pollController = null
  busy = false
  baseline = false
  contentController?.abort()
  contentController = null
  stopStream()
  stopPulses()
}

onMounted(() => {
  alive = true
  document.body.classList.add('workflow-page')
  document.addEventListener('visibilitychange', onVisibility)
  nowMs.value = Date.now()
  clockTimer = setInterval(() => { nowMs.value = Date.now() }, 1000)
  error.value = ''
  baseline = false
  loadWorkflow()
})

onUnmounted(() => {
  alive = false
  document.body.classList.remove('workflow-page')
  document.removeEventListener('visibilitychange', onVisibility)
  clearInterval(clockTimer)
  stopAll()
  content.value = null
})

watch(() => ctx?.refreshKey?.value, () => loadWorkflow())
</script>

<template>
  <aside id="list"></aside>

  <section id="pane">
    <div class="wf-shell" :class="{ 'animation-paused': paused, disconnected: Boolean(error) }">
      <div class="wf-top">
        <div>
          <span id="wf-live" class="wf-live" :class="{ stale: Boolean(error) }">{{ liveText }}</span>
          <span id="wf-updated" class="wf-note">{{ updatedText }}</span>
        </div>
        <button id="wf-animation" :aria-pressed="String(paused)" @click="toggleAnimation">
          {{ paused ? '恢复动画' : '暂停动画' }}
        </button>
      </div>

      <div class="wf-stats">
        <div v-for="stat in stats" :key="stat.label" :class="{ attention: stat.attention }">
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value ?? '—' }}</strong>
          <small>{{ stat.note }}</small>
        </div>
      </div>

      <div v-if="error" class="wf-alert" role="status">
        {{ error }}{{ data ? ' · 下方保留最近快照，状态及倒计时已暂停。' : '' }}
      </div>
      <div v-if="sourceNote" class="wf-note wf-source-note">{{ sourceNote }}。队列中已确认的阶段仍会显示。</div>
      <div v-if="data?.active_more" class="wf-alert">当前展示最早的 500 条待处理记录。更多记录请在收发队列分页查看。</div>

      <section class="wf-overview">
        <button id="wf-overview" :aria-expanded="String(overview)" @click="toggleOverview">
          {{ overview ? '收起' : '展开' }}服务流转概览 <span>{{ modelLabel() }} · {{ modelRoute }}</span>
        </button>
        <div v-if="overview" class="wf-canvas">
          <div class="wf-diagram">
            <template v-if="data?.model?.via_butler === false">
              <WorkflowNode v-bind="nodeProps('model', modelLabel(), '直接接入 · 公开摘要、工具进度与回复正文', '✦', 8)"
                @select="selectMessage" @more="toggleMore" />
              <WorkflowWires band="model" :paths="DIRECT_MODEL_PATHS" :traced="tracedEdges" :color="traceColor" />
              <div class="wf-queue-pair">
                <WorkflowNode v-bind="nodeProps('inbox', '收件队列', 'wxbot · 连续消息合并', '收', 8)"
                  @select="selectMessage" @more="toggleMore" />
                <WorkflowNode v-bind="nodeProps('outbox', '发件队列', 'wxbot · 按句发送与确认', '发', 8)"
                  @select="selectMessage" @more="toggleMore" />
              </div>
              <WorkflowWires band="wechat" :paths="WECHAT_PATHS" :traced="tracedEdges" :color="traceColor" />
              <div class="wf-hub-row">
                <WorkflowNode v-bind="nodeProps('wxbot', 'wxbot', '微信收件与发送确认', 'W', 2)"
                  @select="selectMessage" @more="toggleMore" />
              </div>
            </template>

            <template v-else>
              <WorkflowNode v-bind="nodeProps('model', modelLabel(), '模型执行区 · 公开摘要、工具进度与回复正文', '✦', 8)"
                @select="selectMessage" @more="toggleMore" />
              <WorkflowWires band="model" :paths="MODEL_PATHS" :traced="tracedEdges" :color="traceColor" />
              <div class="wf-hub-row wf-entry-row">
                <div class="wf-telegram-entry">
                  <WorkflowNode
                    v-bind="nodeProps('telegram', 'Telegram', '机器人收件 · 累计 ' + (data?.counts?.telegram || 0) + ' 条', 'T', 2)"
                    @select="selectMessage" @more="toggleMore"
                  />
                </div>
                <svg class="wf-telegram-wire" viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
                  <defs>
                    <marker id="wf-tg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                      <path d="M0 0 L10 5 L0 10z" fill="context-stroke" />
                    </marker>
                  </defs>
                  <g id="wf-edge-telegram" class="wf-wire" :class="{ traced: tracedEdges.has('telegram') }"
                    :style="{ '--trace-color': traceColor }">
                    <path class="wf-wire-line" d="M245 50 H278" marker-end="url(#wf-tg-arrow)" />
                    <path class="wf-packet" d="M245 50 H278" pathLength="100" />
                  </g>
                </svg>
                <WorkflowNode v-bind="nodeProps('butler', 'Butler', '身份 · 角色 · 权限 · 调度', 'B', 2)"
                  @select="selectMessage" @more="toggleMore" />
              </div>
              <WorkflowWires band="queues" :paths="QUEUE_PATHS" :traced="tracedEdges" :color="traceColor" />
              <div class="wf-queue-pair">
                <WorkflowNode v-bind="nodeProps('inbox', '收件队列', 'wxbot · 合并连续消息 / 等待提交', '收', 8)"
                  @select="selectMessage" @more="toggleMore" />
                <WorkflowNode v-bind="nodeProps('outbox', '发件队列', 'wxbot · 按会话顺序发送', '发', 8)"
                  @select="selectMessage" @more="toggleMore" />
              </div>
              <WorkflowWires band="wechat" :paths="WECHAT_PATHS" :traced="tracedEdges" :color="traceColor" />
              <div class="wf-hub-row">
                <WorkflowNode v-bind="nodeProps('wxbot', 'wxbot', '微信收件与发送确认', 'W', 2)"
                  @select="selectMessage" @more="toggleMore" />
              </div>
            </template>
          </div>
          <div class="wf-legend"><i></i> 新事件传输 <em></em> 所选消息经过的路径</div>
        </div>
      </section>

      <section class="wf-sidebar">
        <div class="wf-section-heading">
          <h2>实时消息</h2>
          <span>{{ visible.length }} 条已载入</span>
          <button id="wf-clear-failed" :disabled="deleting || !counts.closed_issues" @click="deleteWorkflow('failed')">
            清理已结束异常 ({{ counts.closed_issues ?? 0 }})
          </button>
        </div>
        <div class="wf-tabs">
          <button v-for="item in SCOPES" :key="item[0]" :data-wf-scope="item[0]" :class="{ on: scope === item[0] }"
            @click="scope = item[0]">{{ item[1] }} <b>{{ countInScope(item[0]) }}</b></button>
        </div>
        <p v-if="notice" class="wf-action-notice" role="status">{{ notice }}</p>
        <div class="wf-message-layout" :class="{ 'has-selection': Boolean(selectedMessage) }">
          <div class="wf-feed">
            <div v-for="message in scopedMessages" :key="message.id" class="wf-card">
              <button
                class="wf-message"
                :class="{ issue: message.scope === 'issues', selected: selected === message.id }"
                :data-focus-key="'wf-feed-' + message.id"
                :data-wf-select="message.id"
                :style="{ '--identity': colorOf(message) }"
                :aria-label="'查看 ' + message.contact + ' 消息 ' + message.id"
                @click="selectMessage(message.id)"
              >
                <span class="wf-message-head">
                  <strong>{{ message.contact }}</strong>
                  <span>{{ (WF_STATUS[message.status] || message.status) }}{{ message.at ? ' · ' + hm(message.at) : '' }}</span>
                </span>
                <template v-if="identityVisible(message)">
                  <span class="wf-identity">UID <code>{{ message.uid }}</code><b v-if="message.group">群聊</b></span>
                  <span v-if="message.group" class="wf-member">
                    成员 {{ (message.members || []).length ? (message.members || []).join(' / ') : '未记录' }}
                  </span>
                </template>
                <span class="wf-preview">{{ workflowExcerpt(textOf(message)) }}</span>
                <span v-if="message.error" class="wf-error">{{ workflowErrorSummary(message) }}</span>
              </button>
              <button v-if="message.can_delete === true" class="wf-delete" :data-wf-delete="message.id"
                :aria-label="'从工作流历史移除 ' + message.contact + ' 的记录'" :disabled="deleting"
                @click="deleteWorkflow('single', message.id)">移除</button>
            </div>
            <div v-if="!scopedMessages.length" class="empty">没有匹配的消息</div>
          </div>
          <WorkflowTrace v-if="selectedMessage" :message="selectedMessage" :content="content" :server-now="serverNow"
            @deselect="deselect" @diagnose="diagnose" />
        </div>
        <p class="wf-note">
          点选消息查看正文与流转。可按用户、UID、群成员及 ID 搜索。{{ data?.history_more ? '历史仅显示最近 60 轮。' : '' }}
        </p>
      </section>

      <details class="wf-recent" data-detail="workflow-recent">
        <summary>最近事件 · {{ recentEvents.length ? fullTime(recentEvents[0].e.ts) : '等待收件' }}</summary>
        <div v-for="item in recentEvents" :key="item.m.id + ':' + item.e.key">
          <time>{{ fullTime(item.e.ts) }}</time>
          <b>{{ item.m.contact }}</b>
          <span>{{ stageLabel(item.e.stage) }} · {{ statusLabel(item.e.status) }}</span>
        </div>
      </details>
    </div>
  </section>
</template>
