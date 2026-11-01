<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiGet, fullTime } from '../api'
import { readPreference, savePreference } from '../prefs'

const props = defineProps({ tab: { type: String, default: 'knowledge' } })
const ctx = inject('logWebCtx', null)

const PAGE_SIZE = 50

const data = ref(null)
const failure = ref('')
const owner = ref(readPreference('kbOwner', ''))
const session = ref('')
const offset = ref(0)
let request = 0
let debounce = null

// 关键词走服务端 LIKE 全库搜索，不受本页分页影响。
const query = computed(() => String(ctx?.search?.[props.tab] || '').trim())
const rows = computed(() => data.value?.rows || [])
// 一人一库：左栏直接列目录里的人和各自的条数，选中的是人而不是会话名。
const owners = computed(() => data.value?.owners || [])
const current = computed(() => owners.value.find(item => item.owner === owner.value) || null)
// 一个人可能同时在私聊和几个群里说过话：左栏仍按人一行，会话维度收成右栏的筛选。
const sessions = computed(() => current.value?.sessions || [])
const activeSession = computed(() => sessions.value.find(item => keyOf(item) === session.value) || null)
const total = computed(() => data.value?.total || 0)
const hasMore = computed(() => Boolean(data.value?.has_more))
const recorded = computed(() => Boolean(data.value?.available))
const failedRows = computed(() => rows.value.filter(row => row.outcome === 'error').length)
const emptyText = computed(() => (recorded.value
  ? '当前筛选下没有对话记录'
  : '尚未记录任何对话'))
const emptyHint = computed(() => (recorded.value ? '' : '这一页只读取原文，等下一轮对话进来后自动出现。'))

watch(owner, value => {
  savePreference('kbOwner', value)
  session.value = ''          // 换人不继承上一个人的会话筛选
  offset.value = 0
  load()
})
watch(query, () => {
  clearTimeout(debounce)
  debounce = setTimeout(() => { offset.value = 0; load() }, 250)
})
watch(() => ctx?.refreshKey?.value, () => load())
onMounted(load)
onUnmounted(() => clearTimeout(debounce))

async function load() {
  const mine = ++request
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset.value) })
  if (owner.value) params.set('owner', owner.value)
  if (activeSession.value) {
    params.set('contact', activeSession.value.contact)
    if (activeSession.value.channel_type) params.set('channel_type', activeSession.value.channel_type)
  }
  if (query.value) params.set('q', query.value)
  try {
    const payload = await apiGet('/api/knowledge?' + params.toString())
    if (mine !== request) return
    data.value = payload
    failure.value = ''
    if (ctx?.markRefreshed) ctx.markRefreshed()
  } catch (err) {
    if (mine !== request) return
    data.value = null
    failure.value = err.message || '对话记录载入失败'
  }
}

function selectOwner(value) {
  if (owner.value === value) return
  owner.value = value
}

function clearOwner() {
  selectOwner('')
}

// 会话用 contact + channel_type 标识：同名的私聊和群聊是两回事，不能只靠名字。
function keyOf(item) {
  return item.contact + '\u0000' + (item.channel_type || '')
}

function sessionText(item) {
  if (item.channel_type === 'group') return '群聊 ' + item.contact
  if (item.channel_type === 'dm') return '私聊 ' + item.contact
  return item.contact
}

// 左栏副标题：一个人有几个会话就看几个，超过两个折成「等 N 个会话」。
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

function badgeOf(row) {
  if (row.outcome === 'error') return { text: '本轮失败', cls: 'sb-error' }
  if (row.outcome === 'silent') return { text: '未回复', cls: 'sb-manual' }
  return { text: row.channel_type === 'group' ? '群聊' : '私聊', cls: 'sb-ok' }
}
</script>

<template>
  <aside id="list">
    <div class="user" :class="{ sel: !owner }" role="button" tabindex="0" @click="clearOwner"
         @keydown.enter.prevent="clearOwner" @keydown.space.prevent="clearOwner">
      <div class="nm">全部会话</div>
      <div class="st">按时间倒序查看所有人的原文</div>
    </div>
    <div
      v-for="item in owners"
      :key="'kb-' + item.owner"
      class="user"
      :class="{ sel: owner === item.owner }"
      role="button"
      tabindex="0"
      @click="selectOwner(item.owner)"
      @keydown.enter.prevent="selectOwner(item.owner)"
      @keydown.space.prevent="selectOwner(item.owner)"
    >
      <div class="nm">{{ item.name }}</div>
      <div class="st">{{ sessionSummary(item) }}，{{ item.episodes }} 条原文，{{ item.facts }} 条事实</div>
    </div>
    <div v-if="data && !owners.length" class="st">还没有可筛选的联系人</div>
  </aside>

  <section id="pane">
    <div class="head">
      <h2>对话记录 · {{ current ? current.name : '全部会话' }}</h2>
      <div v-if="data" class="monitor-grid">
        <span class="chip">共 <b>{{ total }}</b> 条</span>
        <span class="chip">本页 <b>{{ rows.length }}</b> 条</span>
        <span class="chip">本页失败 <b class="warn">{{ failedRows }}</b></span>
      </div>
      <div v-if="sessions.length > 1" class="session-bar">
        <button type="button" class="chip" :class="{ on: !session }"
                :aria-pressed="!session" @click="selectSession('')">
          全部会话
        </button>
        <button v-for="item in sessions" :key="'sess-' + keyOf(item)"
                type="button" class="chip" :class="{ on: session === keyOf(item) }"
                :aria-pressed="session === keyOf(item)" @click="selectSession(keyOf(item))">
          {{ sessionText(item) }}<b class="n">{{ item.count }}</b>
        </button>
      </div>
      <div class="monitor-note">
        每一轮对话的用户原文与机器人回复，只读留存，最新在前。本页不提供删除与编辑。
      </div>
      <div v-if="failure" class="monitor-note warn">{{ failure }}</div>
    </div>

    <div v-if="!data" class="empty">{{ failure || '正在读取对话记录…' }}</div>

    <template v-else>
      <div v-if="!rows.length" class="empty">
        {{ emptyText }}
        <div v-if="emptyHint" class="monitor-note">{{ emptyHint }}</div>
      </div>

      <div v-else class="monitor-table-wrap">
        <table class="monitor-table kb-table">
          <thead>
            <tr><th>时间</th><th>联系人</th><th>用户</th><th>机器人</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in rows"
              :key="'kb-row-' + index"
              :class="{ 'kb-failed': row.outcome === 'error' }"
            >
              <td class="kb-when">{{ fullTime(row.at) }}</td>
              <td class="kb-who">
                {{ row.contact }}
                <div><span class="sbadge" :class="badgeOf(row).cls">{{ badgeOf(row).text }}</span></div>
              </td>
              <td class="kb-text">{{ row.user_text || '（空）' }}</td>
              <td class="kb-text kb-reply">
                <template v-if="row.reply_text">{{ row.reply_text }}</template>
                <span v-else class="kb-gap">{{ row.outcome === 'error' ? '本轮失败，没有产生回复' : '没有回复' }}</span>
              </td>
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
