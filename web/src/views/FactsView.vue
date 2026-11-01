<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiGet, apiPost, fullTime } from '../api'
import { readPreference, savePreference } from '../prefs'

const props = defineProps({ tab: { type: String, default: 'facts' } })
const ctx = inject('logWebCtx', null)

const PAGE_SIZE = 50
const KINDS = {
  profile: '身份背景',
  preference: '偏好习惯',
  personality: '性格',
  goal: '目标',
  relation: '关系',
  event: '约定事件',
  topic: '关注话题'
}

const data = ref(null)
const failure = ref('')
const extract = ref(null)       // 自动提炼状态：开关、上次结果、下次时间
const extractError = ref('')
const extractNote = ref('')     // 刚点完「立即提炼」的即时反馈
const extracting = ref(false)
const owner = ref(readPreference('factOwner', ''))
const session = ref('')
const offset = ref(0)
let request = 0
let debounce = null
let extractTimers = []

const query = computed(() => String(ctx?.search?.[props.tab] || '').trim())
const rows = computed(() => data.value?.rows || [])
const owners = computed(() => data.value?.owners || [])
const current = computed(() => owners.value.find(item => item.owner === owner.value) || null)
// 事实没有 channel_type 列，会话只能按 contact 分；同一个人有多份来源时才需要再缩一层。
const sessions = computed(() => current.value?.sessions || [])
const activeSession = computed(() => sessions.value.find(item => keyOf(item) === session.value) || null)
const total = computed(() => data.value?.total || 0)
const hasMore = computed(() => Boolean(data.value?.has_more))
const recorded = computed(() => Boolean(data.value?.available))
const lowConfidence = computed(() => rows.value.filter(row => Number(row.confidence) < 0.5).length)
const emptyText = computed(() => (recorded.value
  ? '当前筛选下没有提炼出事实'
  : '还没有提炼过任何事实'))
const emptyHint = computed(() => (recorded.value
  ? ''
  : '新对话进来后，自动提炼会在消息间隙把原文整理成事实；本页只读。'))
const extractReady = computed(() => Boolean(extract.value && extract.value.available !== false))
const extractWarn = computed(() => Boolean(extractError.value)
  || extract.value?.available === false
  || (extractReady.value && !extract.value.auto_extract))
// 状态条只报事实：开没开、上次写了多少、下次什么时候；不摆装饰性状态灯。
const extractLine = computed(() => {
  if (extractError.value) return extractError.value
  const info = extract.value
  if (!info) return '正在读取自动提炼状态…'
  if (info.available === false) return '读不到自动提炼状态：' + (info.error || 'Butler 未响应')
  if (extractNote.value) return extractNote.value
  if (!info.knowledge_enabled) return '知识库已关闭，提炼不会运行。'
  if (!info.auto_extract) return '自动提炼未开启，只能手动点「立即提炼」。'
  const rows = info.last_report?.owners || []
  const written = rows.reduce((sum, row) => sum + Number(row.written || 0), 0)
  const broken = rows.find(row => row.error)
  if (broken) return '上次提炼失败（' + broken.error + '），' + clock(info.next_run_at) + ' 再试'
  if (info.failures) {
    return '连续失败 ' + info.failures + ' 次（' + (info.last_error || '未知') + '），'
      + clock(info.next_run_at) + ' 再试'
  }
  if (!info.last_run_at) return '还没提炼过，下次约 ' + clock(info.next_run_at) + '，一批 ' + info.batch + ' 条'
  return '上次提炼 ' + clock(info.last_run_at) + '，写入 ' + written
    + ' 条；下次约 ' + clock(info.next_run_at)
})

watch(owner, value => {
  savePreference('factOwner', value)
  session.value = ''          // 换人不继承上一个人的会话筛选
  offset.value = 0
  load()
})
watch(query, () => {
  clearTimeout(debounce)
  debounce = setTimeout(() => { offset.value = 0; load() }, 250)
})
watch(() => ctx?.refreshKey?.value, () => { load(); loadExtract() })
onMounted(() => { load(); loadExtract() })
onUnmounted(() => {
  clearTimeout(debounce)
  clearExtractTimers()
})

async function load() {
  const mine = ++request
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset.value) })
  if (owner.value) params.set('owner', owner.value)
  if (activeSession.value) params.set('contact', activeSession.value.contact)
  if (query.value) params.set('q', query.value)
  try {
    const payload = await apiGet('/api/knowledge/facts?' + params.toString())
    if (mine !== request) return
    data.value = payload
    failure.value = ''
    if (ctx?.markRefreshed) ctx.markRefreshed()
  } catch (err) {
    if (mine !== request) return
    data.value = null
    failure.value = err.message || '知识库载入失败'
  }
}

// 状态只回答「下次什么时候跑、上次写了多少」，不在前端判断要不要跑。
async function loadExtract() {
  try {
    extract.value = await apiGet('/api/knowledge/extract')
    extractError.value = ''
  } catch (err) {
    extract.value = null
    extractError.value = err.message || '无法读取自动提炼状态'
  }
}

async function runExtract() {
  if (extracting.value) return
  extracting.value = true
  extractNote.value = ''
  try {
    const body = {}
    if (owner.value) body.owner = owner.value   // 选中某人时只提炼他，和左栏保持一致
    await apiPost('/api/knowledge/extract', body)
    extractError.value = ''
    extractNote.value = '已开始提炼，结果稍后出现在下面这张表里'
    scheduleExtractRefresh()
  } catch (err) {
    extractError.value = err.message || '触发失败'
  } finally {
    extracting.value = false
  }
}

// 后台一轮要几十秒：先刷状态，再刷表格；反馈文案最后自己消失。
function scheduleExtractRefresh() {
  clearExtractTimers()
  extractTimers.push(setTimeout(loadExtract, 4000))
  extractTimers.push(setTimeout(() => { loadExtract(); load() }, 15000))
  extractTimers.push(setTimeout(() => { extractNote.value = '' }, 60000))
}

function clearExtractTimers() {
  while (extractTimers.length) clearTimeout(extractTimers.pop())
}

// 今天只显示时分，跨天补上日期，避免把明天看成今天。
function clock(value) {
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds <= 0) return '稍后'
  const at = new Date(seconds * 1000)
  const pad = n => String(n).padStart(2, '0')
  const time = pad(at.getHours()) + ':' + pad(at.getMinutes())
  return at.toDateString() === new Date().toDateString()
    ? time
    : pad(at.getMonth() + 1) + '-' + pad(at.getDate()) + ' ' + time
}

function selectOwner(value) {
  if (owner.value === value) return
  owner.value = value
}

function clearOwner() {
  selectOwner('')
}

// 会话用 contact 标识；事实表没有 channel_type，同名的私聊与群聊分不开也不假装能分。
function keyOf(item) {
  return item.contact + '\u0000' + (item.channel_type || '')
}

function sessionText(item) {
  if (item.channel_type === 'group') return '群聊 ' + item.contact
  if (item.channel_type === 'dm') return '私聊 ' + item.contact
  return item.contact
}

// 左栏副标题：会话超过两个时折成「等 N 个会话」，不把侧栏撑高。
function sessionSummary(item) {
  const list = item.sessions || []
  if (!list.length) return item.channel_type === 'group' ? '群聊' : '私聊'
  const head = list.slice(0, 2).map(sessionText)
  return list.length > head.length
    ? head.join('、') + ' 等 ' + list.length + ' 个会话'
    : head.join('、')
}

function selectSession(value) {
  if (session.value === value) return
  session.value = value
  offset.value = 0
  load()
}

function pageBy(delta) {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  load()
}

function kindOf(row) {
  return KINDS[row.kind] || KINDS.topic
}

function percent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return Math.round(Math.max(0, Math.min(1, number)) * 100) + '%'
}
</script>

<template>
  <aside id="list">
    <div class="user" :class="{ sel: !owner }" role="button" tabindex="0" @click="clearOwner"
         @keydown.enter.prevent="clearOwner" @keydown.space.prevent="clearOwner">
      <div class="nm">全部知识</div>
      <div class="st">按提炼时间倒序查看所有人的事实</div>
    </div>
    <div
      v-for="item in owners"
      :key="'fact-' + item.owner"
      class="user"
      :class="{ sel: owner === item.owner }"
      role="button"
      tabindex="0"
      @click="selectOwner(item.owner)"
      @keydown.enter.prevent="selectOwner(item.owner)"
      @keydown.space.prevent="selectOwner(item.owner)"
    >
      <div class="nm">{{ item.name }}</div>
      <div class="st">{{ sessionSummary(item) }}，{{ item.facts }} 条事实，{{ item.episodes }} 条原文</div>
    </div>
    <div v-if="data && !owners.length" class="st">还没有可筛选的联系人</div>
  </aside>

  <section id="pane">
    <div class="head">
      <h2>知识库 · {{ current ? current.name : '全部知识' }}</h2>
      <div v-if="data" class="monitor-grid">
        <span class="chip">共 <b>{{ total }}</b> 条</span>
        <span class="chip">本页 <b>{{ rows.length }}</b> 条</span>
        <span class="chip">低置信 <b class="warn">{{ lowConfidence }}</b></span>
      </div>
      <div v-if="sessions.length > 1" class="session-bar">
        <button type="button" class="chip" :class="{ on: !session }"
                :aria-pressed="!session" @click="selectSession('')">
          全部来源
        </button>
        <button v-for="item in sessions" :key="'fsess-' + keyOf(item)"
                type="button" class="chip" :class="{ on: session === keyOf(item) }"
                :aria-pressed="session === keyOf(item)" @click="selectSession(keyOf(item))">
          {{ sessionText(item) }}<b class="n">{{ item.count }}</b>
        </button>
      </div>
      <div v-if="extract || extractError" class="extract-bar">
        <div class="note" :class="{ warn: extractWarn }">{{ extractLine }}</div>
        <button v-if="extractReady" type="button" :disabled="extracting" @click="runExtract">
          {{ extracting ? '正在提炼…' : '立即提炼' }}
        </button>
      </div>
      <div class="monitor-note">
        从对话原文里提炼的长期事实，只读留存；新的对话进来后由自动提炼整理。
      </div>
      <div v-if="failure" class="monitor-note warn">{{ failure }}</div>
    </div>

    <div v-if="!data" class="empty">{{ failure || '正在读取知识库…' }}</div>

    <template v-else>
      <div v-if="!rows.length" class="empty">
        {{ emptyText }}
        <div v-if="emptyHint" class="monitor-note">{{ emptyHint }}</div>
      </div>

      <div v-else class="monitor-table-wrap">
        <table class="monitor-table kb-table fact-table">
          <thead>
            <tr><th>时间</th><th>联系人</th><th>类型</th><th>事实</th><th>原话</th><th>置信</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rows" :key="'fact-row-' + index">
              <td class="kb-when">{{ fullTime(row.created) }}</td>
              <td class="kb-who">{{ row.contact }}</td>
              <td class="kb-who"><span class="sbadge sb-ok">{{ kindOf(row) }}</span></td>
              <td class="kb-text">
                <div v-if="row.fact_key" class="fact-key">{{ row.fact_key }}</div>
                {{ row.fact_value }}
              </td>
              <td class="kb-text kb-quote">
                <template v-if="row.quote">{{ row.quote }}</template>
                <span v-else class="kb-gap">没有引用原话</span>
              </td>
              <td class="kb-when kb-conf">{{ percent(row.confidence) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination">
        <button :disabled="!offset" @click="pageBy(-1)">上一页</button>
        <span>第 {{ Math.floor(offset / PAGE_SIZE) + 1 }} 页 · 共 {{ total }} 条</span>
        <button :disabled="!hasMore" @click="pageBy(1)">下一页</button>
      </div>
    </template>
  </section>
</template>
