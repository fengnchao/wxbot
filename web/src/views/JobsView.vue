<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost, fullTime } from '../api'
import { readPreference, savePreference } from '../prefs'

const props = defineProps({ tab: { type: String, default: 'jobs' } })
const ctx = inject('logWebCtx', null)

const JSTATE = {
  active: ['运行中', 'jb-active'],
  paused: ['已暂停', 'jb-paused'],
  done: ['已完成', 'jb-done'],
  error: ['出错', 'jb-error']
}
const JTYPE = { 1: 'type=1 单发', 2: 'type=2 群发' }
const JMT = { 1: '新闻消息', 2: '问候消息', 3: '其他' }
const JSRC = {
  profile: '按 Profile 归属',
  script: '按 script 配置',
  prompt: '按 prompt 归属',
  'script-target': '脚本内置目标',
  'script-profile': '脚本内置 Profile'
}

const data = ref(null)
const loading = ref(true)
const error = ref('')
const message = ref('')
const deleting = ref('')
const uid = ref(readPreference('jobUid', 'all'))
const showDone = ref(readPreference('jobShowDone', false))
let request = 0

const query = computed(() => String(ctx?.search?.[props.tab] || '').trim().toLowerCase())
const users = computed(() => (Array.isArray(data.value?.users) ? data.value.users : []))
const totalCount = computed(() => Number(data.value?.count) || 0)

watch(uid, value => savePreference('jobUid', value))
watch(showDone, value => savePreference('jobShowDone', value))
watch(users, list => {
  if (uid.value !== 'all' && !list.some(item => item.uid === uid.value)) uid.value = 'all'
})
watch(() => ctx?.refreshKey?.value, () => load())
onMounted(load)

function matches(...values) {
  const q = query.value
  return !q || values.some(value => String(value ?? '').toLowerCase().includes(q))
}

function visible(job) {
  return (showDone.value || job.ui_state !== 'done') &&
    matches(job.name, job.uid, job.deliver, job.ui_state, job.last_error, job.job_id)
}

function stats(list) {
  return {
    count: list.length,
    active: list.filter(job => job.ui_state === 'active').length,
    paused: list.filter(job => job.ui_state === 'paused').length,
    done: list.filter(job => job.ui_state === 'done').length,
    error: list.filter(job => job.ui_state === 'error').length
  }
}

const allStats = computed(() => stats(users.value.flatMap(item => item.jobs || []).filter(visible)))
const hiddenAll = computed(() => Math.max(0, totalCount.value - allStats.value.count))

const navUsers = computed(() => users.value.map(item => ({
  item,
  shown: stats((item.jobs || []).filter(visible))
})))

const sections = computed(() => {
  const list = uid.value === 'all' ? users.value : users.value.filter(item => item.uid === uid.value)
  return list.slice()
    .sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN'))
    .map(item => {
      const jobs = item.jobs || []
      const shown = jobs.filter(visible)
      return { item, shown, stats: stats(shown), hidden: jobs.length - shown.length }
    })
})

const hiddenIn = computed(() => sections.value.reduce((sum, row) => sum + row.hidden, 0))
const anyShown = computed(() => sections.value.some(row => row.shown.length))

function uidText(item) {
  return item.uid === 'global' ? '群发 · 收件人由字典决定' : (item.uid_display || item.uid || '')
}

function badge(job) {
  return JSTATE[job.ui_state] || ['?', 'jb-paused']
}

function toEpoch(value) {
  if (!value) return null
  if (typeof value === 'number') return value
  const stamp = Date.parse(value)
  return Number.isNaN(stamp) ? null : stamp / 1000
}

function rows(job) {
  const detail = []
  const failure = job.last_delivery_error || job.last_error || ''
  const next = toEpoch(job.next_run_at)
  const last = toEpoch(job.last_run_at)
  detail.push({ label: '计划', text: job.schedule || '-' })
  detail.push({ label: '下次跑', text: next ? fullTime(next) : '-' })
  detail.push({
    label: '上次跑',
    text: (last ? fullTime(last) : '-') + (job.last_status ? ' · ' + job.last_status : '')
  })
  detail.push({ label: '投递到', text: job.deliver || '-', note: JSRC[job.uid_source] || '' })
  detail.push({
    label: '类型',
    text: (job.script ? 'script ' + job.script : (job.no_agent ? 'no_agent' : 'agent')) +
      (job.repeat ? ' · ' + job.repeat : '')
  })
  if (job.push_type || job.message_type) {
    const bits = []
    if (job.push_type) bits.push(JTYPE[job.push_type] || 'type=' + job.push_type)
    if (job.message_type) bits.push('messageType=' + job.message_type + '（' + (JMT[job.message_type] || '?') + '）')
    if (job.scope === 'global') bits.push('收件人按「用户分组」字典')
    detail.push({ label: '推送', text: bits.join(' · ') })
  }
  if (failure) detail.push({ label: '错误', text: '', failure })
  return detail
}

async function load() {
  const mine = ++request
  if (!data.value) loading.value = true
  try {
    const payload = await apiGet('/api/jobs')
    if (mine !== request) return
    data.value = payload
    error.value = ''
    if (ctx?.markRefreshed) ctx.markRefreshed()
  } catch (err) {
    if (mine !== request) return
    error.value = err.message || String(err)
  } finally {
    if (mine === request) loading.value = false
  }
}

async function remove(job) {
  if (deleting.value) return
  if (!job.can_delete) {
    error.value = job.delete_reason || '此任务请到对应调度器删除'
    return
  }
  const ask = '删除定时任务「' + job.name + '」？\n删除后不再执行，已经发送的消息不会撤回。'
  if (typeof window !== 'undefined' && typeof window.confirm === 'function' && !window.confirm(ask)) return
  deleting.value = job.job_id
  error.value = ''
  message.value = ''
  try {
    await apiPost('/api/jobs/delete', {
      job_id: job.job_id,
      version: job.delete_version,
      acknowledge: true
    }, 'X-Wxbot-Job-Action')
    message.value = '已删除定时任务「' + job.name + '」'
  } catch (err) {
    error.value = err.message || '删除请求失败，请刷新确认任务状态'
    deleting.value = ''
    return
  }
  deleting.value = ''
  await load()
}
</script>

<template>
  <Teleport to="#page-tools">
    <button :class="{ on: showDone }" @click="showDone = !showDone">
      {{ showDone ? '隐藏已完成' : '显示已完成' }}
    </button>
  </Teleport>

  <aside id="list">
    <div class="user" :class="{ sel: uid === 'all' }" @click="uid = 'all'">
      <div class="nm">全部归属</div>
      <div class="st">
        <span>归属 <b>{{ allStats.count }}</b></span>
        <span>活跃 {{ allStats.active }}</span>
        <span>暂停 {{ allStats.paused }}</span>
        <span v-if="allStats.done">已完成 {{ allStats.done }}</span>
        <span v-if="hiddenAll">隐藏已完成 {{ hiddenAll }}</span>
        <span v-if="allStats.error" class="warn">出错 {{ allStats.error }}</span>
      </div>
    </div>
    <div
      v-for="row in navUsers"
      :key="'nav-' + (row.item.uid || row.item.name)"
      class="user"
      :class="{ sel: uid === row.item.uid }"
      @click="uid = row.item.uid"
    >
      <div class="nm">{{ row.item.name }}</div>
      <div class="uid">{{ uidText(row.item) }}</div>
      <div class="st">
        <span>归属 <b>{{ row.shown.count }}</b></span>
        <span>活跃 {{ row.shown.active }}</span>
        <span>暂停 {{ row.shown.paused }}</span>
        <span v-if="row.shown.done">已完成 {{ row.shown.done }}</span>
        <span v-if="row.item.count > row.shown.count">隐藏已完成 {{ row.item.count - row.shown.count }}</span>
        <span v-if="row.shown.error" class="warn">出错 {{ row.shown.error }}</span>
      </div>
    </div>
  </aside>

  <section id="pane">
    <p v-if="error" class="warn" role="alert">{{ error }}</p>
    <p v-if="message" class="monitor-note" role="status">{{ message }}</p>
    <div v-if="loading" class="empty">载入中…</div>
    <div v-else-if="!sections.length" class="empty">没有定时任务</div>
    <div v-else-if="!anyShown" class="empty">
      没有可显示的任务<template v-if="hiddenIn"> —— {{ hiddenIn }} 个已完成已隐藏（点上方「显示已完成」查看）</template>
    </div>
    <template v-else>
      <div v-for="row in sections" :key="'sec-' + (row.item.uid || row.item.name)" class="jsec">
        <h2>
          {{ row.item.name }} <span class="uid">{{ uidText(row.item) }}</span>
          <span class="k">共 {{ row.stats.count }} 个</span>
          <span class="k">活跃 {{ row.stats.active }}</span>
          <span class="k">暂停 {{ row.stats.paused }}</span>
          <span v-if="row.stats.done" class="k">已完成 {{ row.stats.done }}</span>
          <span v-if="row.hidden" class="k">已完成 {{ row.hidden }}（已隐藏）</span>
          <span v-if="row.stats.error" class="k warn">出错 {{ row.stats.error }}</span>
        </h2>
        <div v-if="row.shown.length" class="jgrid">
          <div v-for="job in row.shown" :key="'job-' + job.job_id + '-' + job.profile" class="jcard" :class="job.ui_state">
            <div class="t">
              <span class="nm">{{ job.name }}</span>
              <span class="jbadge" :class="badge(job)[1]">{{ badge(job)[0] }}</span>
            </div>
            <div class="kv">
              <template v-for="(line, index) in rows(job)" :key="'kv-' + index">
                <span class="l">{{ line.label }}</span>
                <span class="v">
                  {{ line.text
                  }}<template v-if="line.note"> <span style="color:var(--fg3)">（{{ line.note }}）</span></template>
                  <template v-if="line.failure"> <span class="err">{{ line.failure }}</span></template>
                </span>
              </template>
            </div>
            <details v-if="job.prompt">
              <summary>prompt 摘要</summary>
              <div class="pre">{{ job.prompt }}</div>
            </details>
            <div class="queue-actions">
              <button
                class="discard"
                :disabled="!job.can_delete || deleting === job.job_id"
                :title="job.can_delete ? '删除后不再执行' : (job.delete_reason || '此任务由其他调度器管理，请到对应调度器删除')"
                @click="remove(job)"
              >{{ deleting === job.job_id ? '删除中…' : '删除' }}</button>
            </div>
          </div>
        </div>
        <div v-else class="empty" style="padding:12px">该组的任务全部已完成（已隐藏）</div>
      </div>
    </template>
  </section>
</template>
