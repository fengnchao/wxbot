<script setup>
import { computed, inject, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { apiGet, apiPost, fullTime } from '../api'
import { readPreference, savePreference } from '../prefs'
import { takeQueueFocus } from '../queueFocus'

const props = defineProps({ tab: { type: String, default: 'queue' } })
const ctx = inject('logWebCtx', null)

const QUEUE_LABELS = {
  review: '结果待核对（不阻塞）', restart_discard: '重启停止续发', draft_hold: '草稿待人工处理',
  unbatched: '待合并', ready: '待提交模型', processing: '等待模型', waiting_delivery: '回复就绪',
  pending: '待发送', sending: '键入中', confirming: '发送确认中', blocked: '已阻断', uncertain: '结果不确定',
  sent: '已发送', skipped: '已跳过', timeout_discard: '超时丢弃', done: '整轮完成', idle: '空闲',
  pending_capture: '待采集', merging: '合并中', ready_to_merge: '待调度', state_mismatch: '状态待核对',
  completed: '已完成', ok: '完成', failed: '失败', error: '错误', started: '已开始', running: '执行中',
  accepted: '已接受', finished: '已结束', model_failed: '模型失败已结束', batched: '已合并',
  received: 'Butler 已收件', rejected: '已拒绝', not_submitted: '未提交', cancelled: '已取消',
  partial_deleted: '部分已发，其余已删除', preparing: '图片准备中', media_failed: '图片准备失败',
  awaiting_bot: '等待机器人收件'
}
const BAD_STATES = ['blocked', 'uncertain', 'failed', 'error', 'model_failed', 'rejected', 'not_submitted', 'media_failed']
const OK_STATES = ['done', 'sent', 'skipped', 'completed', 'ok', 'finished']
const ACTION_LABELS = { retry: '重试', sent: '确认已发', skip: '立即丢弃' }
const STATE_OPTIONS = [
  ['active', '未完成任务'], ['all', '全部状态'], ['unbatched', '待合并'], ['ready', '待提交模型'],
  ['processing', '等待模型'], ['waiting_delivery', '回复就绪'], ['pending', '待发送'],
  ['sending', '键入中'], ['confirming', '发送确认中'], ['blocked', '已阻断'],
  ['uncertain', '结果不确定'], ['done', '整轮完成'], ['sent', '已发送'], ['skipped', '已跳过']
]
const SCOPES = [
  ['all', '全部消息'], ['active', '待处理'], ['issues', '异常待核对'], ['history', '历史记录']
]
const EVENT_LABELS = {
  restart_discard: '重启停止续发', review: '结果待核对，停止本轮续发', timeout: '整轮失败超时结束',
  failed: '发送失败', timeout_discard: '失败超时丢弃', retry: '人工重试', confirm_sent: '人工确认已发',
  manual_discard: '人工丢弃', model_retryable: '模型失败，等待自动重试', model_uncertain: '模型结果未知',
  model_retry: '模型自动重试', model_abandoned: '模型失败已结束'
}

const data = ref(null)
const qError = ref('')
const qBusy = ref(false)
const qMessage = ref('')
const qActionFailed = ref(false)
const qContact = ref('')
const qState = ref(readPreference('qState', 'all'))
const qScope = ref(readPreference('qScope', 'all'))
const offsets = reactive({ inbox: 0, batches: 0, outbox: 0, rounds: 0, telegram: 0 })
const nowSec = ref(Date.now() / 1000)
let request = 0
let timer = null

// 工作流页的「在收发队列中查看 / 处理」会带一次筛选条件，正常进入时不受影响。
const incomingFocus = takeQueueFocus()
if (incomingFocus) {
  qContact.value = incomingFocus.contact || ''
  qState.value = incomingFocus.state || 'all'
  qScope.value = incomingFocus.scope || 'all'
}

const query = computed(() => String(ctx?.search?.[props.tab] || '').trim().toLowerCase())

watch(qState, value => savePreference('qState', value))
watch(qScope, value => savePreference('qScope', value))
watch(() => ctx?.refreshKey?.value, () => load())
onMounted(() => {
  load()
  timer = setInterval(() => { nowSec.value = Date.now() / 1000 }, 1000)
})
onUnmounted(() => clearInterval(timer))

function matches(...values) {
  const q = query.value
  return !q || values.some(value => String(value ?? '').toLowerCase().includes(q))
}

function badgeOf(status) {
  const cls = BAD_STATES.includes(status) ? 'sb-error' : (OK_STATES.includes(status) ? 'sb-ok' : 'sb-manual')
  return { text: QUEUE_LABELS[status] || status, cls }
}

function countdownText(at) {
  if (at == null) return ''
  const left = Math.max(0, Math.ceil(Number(at) - nowSec.value))
  return left ? '剩余 ' + left + ' 秒自动丢弃' : '已到丢弃时间，等待 wxbot 巡检'
}

function recoveryText(row) {
  if (row.retry_at != null) {
    return '下次自动重试：' + fullTime(row.retry_at) + ' · 已尝试 ' + (row.attempts || 0) + '/' + (row.max_attempts || 3) + ' 次'
  }
  return row.retry_safe === false ? '结果未知，不自动重放本条；到期结束失败批次并放行后续消息' : ''
}

function recordFor(row, kind) {
  const record = {
    id: row.id || row.record_id,
    kind,
    contact: row.contact,
    expected_state: row.state,
    expected_finished_at: row.finished_at ?? null
  }
  if (kind === 'batches') record.expected_attempts = row.attempts
  return record
}

function pendingOutbox(buckets) {
  return Object.entries(buckets || {})
    .filter(([state]) => !['sent', 'skipped'].includes(state))
    .reduce((sum, [, count]) => sum + count, 0)
}

/** 会话摘要里已带记录时，操作按钮显示在下方任务行，避免重复。 */
function actionsShownInList(reason) {
  const rows = reason.record_kind === 'outbox'
    ? (data.value?.rounds || [])
      .filter(row => matches(row.contact, row.preview, row.error, row.id))
      .flatMap(row => row.parts || [])
    : (data.value?.[reason.record_kind] || []).filter(row => matches(row.contact, row.preview, row.error, row.id))
  return rows.some(row => String(row.id) === String(reason.record_id) && row.actions?.length)
}

const navContacts = computed(() => ((data.value?.contacts) || []).map(contact => ({
  ...contact,
  badge: badgeOf(contact.reason.code),
  pendingOutbox: pendingOutbox(contact.outbox)
})))

const visibleContacts = computed(() => navContacts.value
  .filter(contact => (qContact.value ? contact.contact === qContact.value : contact.reason.code !== 'idle'))
  .filter(contact => matches(contact.contact, contact.reason.message, contact.reason.error))
  .map(contact => {
    const reason = contact.reason
    const actions = reason.actions || []
    return {
      ...contact,
      reason,
      actions,
      bad: ['blocked', 'uncertain'].includes(reason.code),
      recovery: recoveryText(reason),
      countdown: countdownText(reason.discard_at),
      actionsInList: actions.length ? actionsShownInList(reason) : false,
      reasonRecord: actions.length ? recordFor(reason, reason.record_kind) : null
    }
  }))

function buildTable(kind, rows, page) {
  const pager = page || { total: 0, offset: 0, limit: 50, has_more: false }
  return {
    kind,
    title: kind === 'inbox'
      ? (qScope.value === 'all' ? '微信收件（含已合并）' : '待合并消息')
      : '模型批次',
    page: pager,
    rows: rows.filter(row => matches(row.contact, row.preview, row.error, row.id)).map(row => ({
      ...row,
      badge: badgeOf(row.display_state || (row.resolution === 'timeout' ? 'timeout_discard' : row.state)),
      actions: row.actions || [],
      countdown: countdownText(row.discard_at),
      recovery: kind === 'batches' ? recoveryText(row) : '',
      at: fullTime(row.received_at ?? row.created_at),
      record: recordFor(row, kind)
    }))
  }
}

const inboxTable = computed(() => buildTable('inbox', data.value?.inbox || [], data.value?.pages?.inbox))
const batchesTable = computed(() => buildTable('batches', data.value?.batches || [], data.value?.pages?.batches))

const tableList = computed(() => {
  const list = []
  if (['all', 'active'].includes(qScope.value)) list.push(inboxTable.value)
  list.push(batchesTable.value)
  return list
})

const roundsPage = computed(() => data.value?.pages?.rounds || { total: 0, offset: 0, limit: 50, has_more: false })
const roundRows = computed(() => (data.value?.rounds || [])
  .filter(row => matches(row.contact, row.preview, row.error, row.id))
  .map(row => ({
    ...row,
    badge: badgeOf(row.display_state || row.state),
    at: fullTime(row.created_at),
    countdown: countdownText(row.discard_at),
    parts: (row.parts || []).map(part => ({
      ...part,
      badge: badgeOf(part.display_state || part.state),
      record: recordFor(part, 'outbox')
    }))
  })))

const telegram = computed(() => {
  const payload = data.value?.telegram
  if (!payload) return { missing: true, rows: [], page: { total: 0, offset: 0, limit: 50, has_more: false } }
  if (payload.status !== 'ok') return { error: payload.error, status: payload.status, rows: [], page: payload.page || {} }
  const page = payload.page || { total: 0, offset: 0, limit: 50, has_more: false }
  return {
    page,
    rows: (payload.rows || [])
      .filter(row => matches(row.contact, row.uid, row.id, row.preview, row.reason, row.error, row.targets))
      .map(row => ({
        ...row,
        badge: badgeOf(row.state),
        created: fullTime(row.created_at),
        received: row.received_at ? fullTime(row.received_at) : '未入库',
        deliveries: (row.deliveries || []).map(task => ({
          ...task,
          badge: badgeOf(task.state),
          at: fullTime(task.updated)
        }))
      }))
  }
})

const events = computed(() => (data.value?.events || []).map(event => ({
  ...event,
  label: EVENT_LABELS[event.action] || event.action,
  at: fullTime(event.at)
})))

const statusError = computed(() => {
  const payload = data.value
  return payload && payload.status !== 'ok' ? payload.error : ''
})
const actionsEnabled = computed(() => Boolean(data.value?.actions_enabled))
const telegramTotal = computed(() => Object.values(data.value?.telegram?.counts || {})
  .reduce((sum, value) => sum + value, 0))
const timeoutSeconds = computed(() => {
  const value = Number(data.value?.failure_timeout_seconds)
  return Number.isFinite(value) && value > 0 ? value : 180
})
const totalOf = (which, state) => (data.value?.counts?.[which] || {})[state] || 0
const orderNote = computed(() => {
  const order = ['all', 'history'].includes(qScope.value)
    ? '最新记录在前'
    : qScope.value === 'issues' ? '最早任务在前 · 请先核对实际发送结果' : '按实际处理序号排列'
  const state = qState.value === 'all' ? '全部' : (QUEUE_LABELS[qState.value] || qState.value)
  return order + ' · 状态：' + state + (query.value ? ' · 搜索作用于本页及当前会话摘要' : '')
})

async function load() {
  if (qBusy.value) return
  const mine = ++request
  const params = new URLSearchParams({ contact: qContact.value, state: qState.value, scope: qScope.value, limit: '50' })
  for (const [key, value] of Object.entries(offsets)) params.set(key + '_offset', String(value))
  try {
    const payload = await apiGet('/api/queue?' + params.toString())
    if (mine !== request) return
    data.value = payload
    qError.value = ''
    if (ctx?.markRefreshed) ctx.markRefreshed()
  } catch (err) {
    if (mine !== request) return
    data.value = null
    qError.value = err.message || '队列载入失败'
  }
}

function resetPages() {
  for (const key of Object.keys(offsets)) offsets[key] = 0
}

function selectContact(name) {
  qContact.value = name
  resetPages()
  load()
}

function onState(value) {
  qState.value = value
  resetPages()
  load()
}

function setScope(value) {
  qScope.value = value
  qState.value = 'all'
  resetPages()
  load()
}

function clearFilters() {
  qContact.value = ''
  qState.value = 'all'
  qScope.value = 'all'
  if (ctx?.search) ctx.search[props.tab] = ''
  resetPages()
  load()
}

function pageBy(table, delta) {
  offsets[table.kind] = Math.max(0, table.page.offset + delta * table.page.limit)
  load()
}

function pageTelegram(delta) {
  const page = telegram.value.page
  offsets.telegram = Math.max(0, (page.offset || 0) + delta * (page.limit || 50))
  load()
}

function pageRounds(delta) {
  const page = roundsPage.value
  offsets.rounds = Math.max(0, (page.offset || 0) + delta * (page.limit || 50))
  load()
}

async function performAction(record, action) {
  if (qBusy.value || !record || !ACTION_LABELS[action]) return
  const caution = action === 'retry'
    ? (record.kind === 'outbox'
      ? '请先核对微信实际发送结果，并清理残留草稿。重试可能重复发送，仍在处理的整轮失败期限不会重置；已退出调度的任务明确重试后开启新期限，只重试所选块。'
      : '请先核对模型与工具实际执行结果。重试可能重复执行工具。')
    : action === 'sent'
      ? '请确认已在微信看到这条消息实际发送成功。此操作只登记结果，不再发送。'
      : '此操作放弃这条任务并释放后续队列，保留消息和失败记录。'
  const ask = ACTION_LABELS[action] + ' · ' + record.contact + '\n任务 ' + record.id + '\n\n' + caution
  if (typeof window !== 'undefined' && typeof window.confirm === 'function' && !window.confirm(ask)) return
  qBusy.value = true
  qMessage.value = '正在处理…'
  qActionFailed.value = false
  try {
    await apiPost('/api/queue-action', { ...record, action, acknowledge: true }, 'X-Wxbot-Queue-Action')
    qMessage.value = record.contact + ' · ' + record.id + '：' + ACTION_LABELS[action] + '已登记'
  } catch (err) {
    qActionFailed.value = true
    qMessage.value = err.message || '操作失败'
  } finally {
    qBusy.value = false
  }
  await load()
}

async function deleteUnsent() {
  if (qBusy.value) return
  const ask = '删除所有未发送成功消息\n\n范围：微信和 Telegram 的全部会话，不受当前筛选或分页影响。\n'
    + '删除消息记录并停止后续投递；已发送成功的记录保留。\n'
    + '正在输入、确认发送结果或提交中的任务本次保留，请稍后处理。\n'
    + '尚未实际采集的微信会话继续接收，本次保留。\n微信输入框已有草稿需自行清理。'
  if (typeof window !== 'undefined' && typeof window.confirm === 'function' && !window.confirm(ask)) return
  qBusy.value = true
  qMessage.value = '正在删除…'
  qActionFailed.value = false
  try {
    const payload = await apiPost('/api/queue-delete-unsent', { acknowledge: true }, 'X-Wxbot-Queue-Action')
    const wx = payload.wxbot || {}
    const tg = payload.telegram || {}
    const protectedActive = (wx.protected_active || 0) + (tg.protected_active || 0)
    let text = '已删除：微信 ' + (wx.deleted_messages || 0) + ' 条消息、' + (wx.deleted_deliveries || 0)
      + ' 条投递；Telegram ' + (tg.deleted_messages || 0) + ' 条消息、' + (tg.deleted_deliveries || 0)
      + ' 条投递。本次保留正在处理的任务 ' + protectedActive + ' 个（微信 ' + (wx.protected_active || 0)
      + '，Telegram ' + (tg.protected_active || 0) + '）' + (protectedActive ? '，请稍后处理。' : '。')
    if (wx.drafts_to_clear) text += '另有 ' + wx.drafts_to_clear + ' 个会话的微信输入框草稿需自行清理。'
    if (wx.protected_reads) text += '保留任务中有 ' + wx.protected_reads + ' 个尚未采集的微信会话。'
    qMessage.value = text
  } catch (err) {
    qActionFailed.value = true
    qMessage.value = err.message || '删除失败'
  } finally {
    qBusy.value = false
  }
  await load()
}
</script>

<template>
  <Teleport to="#page-tools">
    <select id="q-state" :value="qState" aria-label="队列状态筛选" @change="onState($event.target.value)">
      <option v-for="option in STATE_OPTIONS" :key="option[0]" :value="option[0]">{{ option[1] }}</option>
    </select>
  </Teleport>

  <aside id="list">
    <div class="user" :class="{ sel: !qContact }" @click="selectContact('')">
      <div class="nm">全部会话</div>
      <div class="st">查看所有用户和群聊的队列</div>
    </div>
    <div
      v-for="contact in navContacts"
      :key="'nav-' + contact.contact"
      class="user"
      :class="{ sel: qContact === contact.contact }"
      @click="selectContact(contact.contact)"
    >
      <div class="nm">
        {{ contact.contact }}
        <span class="sbadge" :class="contact.badge.cls">{{ contact.badge.text }}</span>
      </div>
      <div class="st">待合并 <b>{{ contact.unbatched }}</b> · 待发 <b>{{ contact.pendingOutbox }}</b></div>
      <div class="pv">{{ contact.reason.message }}</div>
    </div>
  </aside>

  <section id="pane">
    <div class="head">
      <h2>收发队列 · {{ qContact || '全部会话' }}</h2>
      <div class="queue-actions">
        <button class="discard" :disabled="qBusy" @click="deleteUnsent">删除所有未发送成功消息</button>
      </div>
      <div v-if="!data" class="empty warn">{{ qError || '正在载入队列…' }}</div>
      <template v-else>
        <div class="monitor-note">适用于全部微信与 Telegram 会话，不受当前筛选或分页影响。</div>
        <div v-if="statusError" class="warn">wxbot 队列：{{ statusError }}</div>
        <div class="monitor-grid">
          <span class="chip">Telegram <b>{{ telegramTotal }}</b></span>
          <span class="chip">全队列待合并 <b>{{ data.counts?.unbatched || 0 }}</b></span>
          <span class="chip">待提交 <b>{{ totalOf('batches', 'ready') }}</b></span>
          <span class="chip">等待模型 <b>{{ totalOf('batches', 'processing') }}</b></span>
          <span class="chip">待发块 <b>{{ totalOf('outbox', 'pending') }}</b></span>
          <span class="chip">异常块 <b class="warn">{{ totalOf('outbox', 'blocked') + totalOf('outbox', 'uncertain') }}</b></span>
        </div>
        <div class="monitor-note">
          同一会话按顺序处理。发件失败从首次失败起最多等待{{ timeoutSeconds }}秒，超时结束本轮剩余分块并保留日志；结果不确定的保留核对记录且不阻塞后续消息。模型确认未提交时最多尝试3次；模型结果未知时不重放，失败满{{ timeoutSeconds }}秒结束旧批次，继续处理后续消息。人工核对按钮在下方异常任务旁，操作前需要确认。
        </div>
        <div v-if="qMessage" class="monitor-note" :class="{ warn: qActionFailed }">{{ qMessage }}</div>
        <div v-if="!actionsEnabled" class="monitor-note warn">请先重启更新后的 wxbot，启用人工核对按钮。</div>
      </template>
    </div>

    <template v-if="data">
      <div class="segmented">
        <button
          v-for="scope in SCOPES"
          :key="scope[0]"
          :class="{ on: qScope === scope[0] }"
          @click="setScope(scope[0])"
        >{{ scope[1] }}</button>
        <button @click="clearFilters">清除全部筛选</button>
      </div>
      <div class="monitor-note">{{ orderNote }}</div>

      <template v-if="qScope !== 'history'">
        <div
          v-for="contact in visibleContacts"
          :key="'reason-' + contact.contact"
          class="queue-reason"
          :class="{ error: contact.bad }"
        >
          <h3>{{ contact.contact }} · <span class="sbadge" :class="contact.badge.cls">{{ contact.badge.text }}</span></h3>
          <div>{{ contact.reason.message }}{{ contact.reason.wait_seconds > 0 ? ' · 约 ' + Math.ceil(contact.reason.wait_seconds) + ' 秒' : '' }}</div>
          <div v-if="contact.reason.error" class="monitor-note warn">{{ contact.reason.error }}</div>
          <div v-if="contact.recovery" class="monitor-note">{{ contact.recovery }}</div>
          <div v-if="contact.countdown" class="monitor-note warn">{{ contact.countdown }}</div>
          <div v-if="contact.actions.length" class="monitor-source">人工核对：先确认微信实际发送结果及输入框草稿，再操作。</div>
          <div v-if="contact.actionsInList" class="monitor-note">在下方对应任务行执行人工核对操作。</div>
          <div v-else-if="contact.actions.length" class="queue-actions">
            <button
              v-for="action in contact.actions"
              :key="action"
              :class="{ discard: action === 'skip' }"
              :disabled="qBusy"
              @click="performAction(contact.reasonRecord, action)"
            >{{ ACTION_LABELS[action] }}</button>
          </div>
        </div>
        <div v-if="!visibleContacts.length" class="monitor-note">没有待处理任务</div>
      </template>

      <h3 class="monitor-section-title">
        Telegram 收件 / 新闻转发 · {{ telegram.page?.total || 0 }} 条
      </h3>
      <div class="monitor-note">按发送者数字 ID 区分用户；收件成功与微信发送成功分别记录。阻塞分段显示前置任务，跨系统未有关联证据时不合并为同一条。</div>
      <div v-if="telegram.missing" class="monitor-note warn">Telegram 队列接口尚未加载，请手动重启 log。</div>
      <div v-else-if="telegram.error" class="monitor-note" :class="{ warn: telegram.status === 'error' }">
        Telegram：{{ telegram.error }}
      </div>
      <template v-else>
        <div v-if="telegram.rows.length" class="monitor-table-wrap">
          <table class="monitor-table">
            <thead><tr><th>用户 / 状态</th><th>内容 / 阻塞原因</th><th>时间 / 去向</th></tr></thead>
            <tbody>
              <tr v-for="row in telegram.rows" :key="row.id">
                <td>{{ row.contact }}<br><span class="sbadge" :class="row.badge.cls">{{ row.badge.text }}</span></td>
                <td class="preview">
                  {{ row.preview }}
                  <div v-if="row.has_media" class="monitor-note">含媒体附件</div>
                  <div class="monitor-note" :class="{ warn: row.error }">{{ row.error || row.reason }}</div>
                  <details :open="Boolean(row.error)">
                    <summary>逐人发送与阻塞详情 · {{ row.deliveries.length }} 段</summary>
                    <div
                      v-for="task in row.deliveries"
                      :key="task.id"
                      class="queue-reason"
                      :class="{ error: ['uncertain', 'blocked', 'not_submitted', 'rejected'].includes(task.state) }"
                    >
                      <b>{{ task.contact }} · 第 {{ task.part }} 段</b>
                      <span class="sbadge" :class="task.badge.cls">{{ task.badge.text }}</span>
                      <div>{{ task.reason }}</div>
                      <div class="monitor-source">{{ task.at }}</div>
                    </div>
                    <div v-if="!row.deliveries.length" class="monitor-note">尚无新闻投递任务，请查看上面的原因。</div>
                    <div v-if="row.deliveries_truncated" class="warn">仅显示前 200 个分段，完整记录保存在接收器数据库。</div>
                  </details>
                </td>
                <td>
                  消息 {{ row.created }}<br>
                  Butler 入库 {{ row.received }}
                  <div>{{ row.targets || '尚未分配接收人' }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="monitor-note">当前筛选下没有 Telegram 消息</div>
        <div class="pagination">
          <button :disabled="!telegram.page?.offset" @click="pageTelegram(-1)">上一页</button>
          <span>第 {{ Math.floor((telegram.page?.offset || 0) / (telegram.page?.limit || 50)) + 1 }} 页 · 共 {{ telegram.page?.total || 0 }} 条</span>
          <button :disabled="!telegram.page?.has_more" @click="pageTelegram(1)">下一页</button>
        </div>
      </template>

      <template v-for="table in tableList" :key="table.kind">
        <h3 class="monitor-section-title">
          {{ table.title }} <span class="monitor-source">{{ table.page.total }} 条，当前显示 {{ table.rows.length }} 条</span>
        </h3>
        <div v-if="table.rows.length" class="monitor-table-wrap">
          <table class="monitor-table">
            <thead><tr><th>会话 / 状态</th><th>内容预览</th><th>时间 / 进度</th></tr></thead>
            <tbody>
              <tr v-for="row in table.rows" :key="table.kind + '-' + row.id">
                <td>{{ row.contact }}<br><span class="sbadge" :class="row.badge.cls">{{ row.badge.text }}</span></td>
                <td class="preview">
                  {{ row.preview }}
                  <div class="monitor-source">{{ row.characters }} 字{{ row.characters > 240 ? '，仅显示前 240 字' : '' }}</div>
                  <div v-if="row.error" class="warn">{{ row.error }}</div>
                  <div v-if="row.countdown" class="monitor-note warn">{{ row.countdown }}</div>
                  <div v-if="row.recovery" class="monitor-note">{{ row.recovery }}</div>
                  <div v-if="row.actions.length" class="queue-actions">
                    <button
                      v-for="action in row.actions"
                      :key="action"
                      :class="{ discard: action === 'skip' }"
                      :disabled="qBusy"
                      @click="performAction(row.record, action)"
                    >{{ ACTION_LABELS[action] }}</button>
                  </div>
                </td>
                <td>
                  {{ row.at }}
                  <div v-if="table.kind === 'outbox'">第 {{ row.part_seq }}/{{ row.part_count }} 块</div>
                  <template v-if="table.kind === 'batches'">
                    <div>已发 {{ row.sent_parts }}/{{ row.part_count }} 块</div>
                    <div>提交次数 {{ row.attempts || 0 }}</div>
                  </template>
                  <div v-if="row.started_at" class="monitor-source">模型开始 {{ fullTime(row.started_at) }}</div>
                  <div v-if="row.submitted_at" class="monitor-source">回车 {{ fullTime(row.submitted_at) }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="monitor-note">当前筛选下没有任务</div>
        <div class="pagination">
          <button :disabled="!table.page.offset" @click="pageBy(table, -1)">上一页</button>
          <span>第 {{ Math.floor(table.page.offset / table.page.limit) + 1 }} 页 · 共 {{ table.page.total }} 条</span>
          <button :disabled="!table.page.has_more" @click="pageBy(table, 1)">下一页</button>
        </div>
      </template>

      <h3 class="monitor-section-title">回复整轮 / 主动推送</h3>
      <div v-for="round in roundRows" :key="'round-' + round.id" class="queue-reason">
        <h3>{{ round.contact }} · <span class="sbadge" :class="round.badge.cls">{{ round.badge.text }}</span></h3>
        <div>{{ round.preview }}</div>
        <div class="monitor-note">已发 {{ round.sent_parts }} / {{ round.part_count }} 块 · {{ round.at }}</div>
        <div v-if="round.error" class="warn">{{ round.error }}</div>
        <div v-if="round.countdown" class="monitor-note warn">{{ round.countdown }}</div>
        <div v-for="part in round.parts.filter(item => item.actions?.length)" :key="'act-' + part.id" class="queue-actions">
          第 {{ part.part_seq }} 块
          <button
            v-for="action in part.actions"
            :key="action"
            :class="{ discard: action === 'skip' }"
            :disabled="qBusy"
            @click="performAction(part.record, action)"
          >{{ ACTION_LABELS[action] }}</button>
        </div>
        <details>
          <summary>查看分段回复</summary>
          <div v-for="part in round.parts" :key="'part-' + part.id" class="monitor-note">
            <b>第 {{ part.part_seq }} 块</b>
            <span class="sbadge" :class="part.badge.cls">{{ part.badge.text }}</span> · {{ part.characters }} 字
            <div>{{ part.preview }}</div>
            <div class="warn">{{ part.error || '' }}</div>
          </div>
        </details>
      </div>
      <div v-if="!roundRows.length" class="monitor-note">当前筛选下没有回复任务</div>
      <div class="pagination">
        <button :disabled="!roundsPage.offset" @click="pageRounds(-1)">上一页</button>
        <span>第 {{ Math.floor((roundsPage.offset || 0) / (roundsPage.limit || 50)) + 1 }} 页 · 共 {{ roundsPage.total || 0 }} 轮</span>
        <button :disabled="!roundsPage.has_more" @click="pageRounds(1)">下一页</button>
      </div>

      <details :open="qScope === 'issues'">
        <summary>失败、自动恢复与人工核对记录</summary>
        <h3 class="monitor-section-title">失败与恢复记录 · 最近50条</h3>
        <div v-if="events.length" class="monitor-table-wrap">
          <table class="monitor-table">
            <thead><tr><th>时间 / 会话</th><th>处理记录</th></tr></thead>
            <tbody>
              <tr v-for="event in events" :key="'event-' + event.seq">
                <td>{{ event.at }}<br>{{ event.contact }}</td>
                <td>
                  <b>{{ event.label }}</b>
                  <div class="monitor-note">{{ event.reason }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="monitor-note">暂无失败或人工处理记录</div>
      </details>
    </template>
  </section>
</template>
