<script setup>
import { computed, inject, onMounted, watch } from 'vue'
import {
  activeId, aliasDraft, aliasVersion, busy, cancelNews, data, dialog, error,
  hbShown, kind, load, loadMemory, loadNews, loadStatus, news, newsBusy, newsDraft,
  newsError, newsMessage, newsVersion, openDialog, pick, query, saveAliases, saveNews,
  section, triggerHeartbeat
} from '../contactState'
import ContactDialog from '../components/ContactDialog.vue'
import HeartbeatStatus from '../components/HeartbeatStatus.vue'
import StructuredEditor from '../components/StructuredEditor.vue'
import UserDialog from '../components/UserDialog.vue'

const ctx = inject('logWebCtx', null)

const FILTERS = [['', '全部'], ['dm', '私聊'], ['group', '群聊'], ['pending', '待补充资料'], ['disabled', '已停用']]
const SUBSCRIPTIONS = { 1: '新闻', 2: '问候', 3: '其他' }
const NEWS_STATUS = {
  sent: '已发送',
  incomplete: '部分未确认，请检查收发队列',
  no_news: '没有可用的新新闻',
  no_subscribers: '没有新闻订阅者',
  legacy_run_exists: '今日模拟任务已有记录，跳过重复推送',
  failed: '执行失败'
}

const rows = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const filter = kind.value
  return (data.value?.rows || []).filter(row => {
    if (needle && !JSON.stringify([row.name, row.id, row.memberships, row.conversations]).toLowerCase().includes(needle)) {
      return false
    }
    if (!filter) return true
    if (filter === row.kind) return true
    if (filter === 'dm' && row.conversations.some(item => item.channel_type === 'dm')) return true
    if (filter === 'disabled' && !row.enabled) return true
    if (filter === 'pending' && (!row.conversations.length ||
      row.conversations.some(item => item.needs_route) ||
      row.memberships.some(member => !member.identity_confirmed))) return true
    return false
  })
})

const current = computed(() => {
  const list = rows.value
  return list.find(row => row.id === activeId.value) || list[0] || null
})

watch(current, row => {
  if (row && row.id !== activeId.value) activeId.value = row.id
}, { immediate: true })

watch(() => ctx?.search?.contacts, value => { query.value = String(value || '') }, { immediate: true })

watch(() => ctx?.refreshKey?.value, () => load())

watch([data, section], () => {
  if (section.value === 'aliases' && aliasDraft.value === null && data.value?.active) initAliases()
})

const newsValues = computed(() => newsDraft.value || news.value?.settings || { categories: [], sources: [], count: 1 })
const aliasJson = computed(() => JSON.stringify(aliasDraft.value || [], null, 2))
// 弹窗按打开内容重建，保证表单一次性初始化。
const CONTACT_DIALOGS = ['create', 'person', 'conversation', 'policy', 'link', 'membership', 'settings']
const isContactDialog = computed(() => CONTACT_DIALOGS.includes(dialog.value?.kind))
const dialogKey = computed(() => dialog.value
  ? dialog.value.kind + ':' + (dialog.value.payload?.id || dialog.value.payload?.row?.id || '')
  : 'none')

onMounted(load)

function avatarOf(row) {
  return /^data:image\/png;base64,/.test(row.avatar || '')
}

function rowNote(row) {
  const bits = [row.kind === 'group' ? '群聊' : row.memberships.length + ' 个所属群 · 共享记忆 ' + row.memory_count + ' 条']
  if (!row.enabled) bits.push('已停用')
  if (row.conversations.some(item => item.needs_route)) bits.push('待补充资料')
  return bits.join(' · ')
}

function subscriptionsText(conversation) {
  return (conversation.subscriptions || []).map(value => SUBSCRIPTIONS[value] || '类型 ' + value).join('、') || '无'
}

function policyText(row, conversation) {
  const policy = conversation.policy || row.policy
  if (conversation.policy) return '会话覆盖角色：' + (conversation.policy.role_skill || '')
  if (row.policy) return '使用默认角色：' + (row.policy.role_skill || '')
  return '尚未绑定角色'
}

function heartbeatOn(row, conversation) {
  return Boolean((conversation.policy || row.policy)?.heartbeat_enabled)
}

function personButtons(row) {
  return row.kind === 'person' && (data.value?.rows || []).some(item => item.id === row.id) &&
    !row.conversations.some(item => item.id === row.id)
}

function openCreate(person = null) {
  openDialog('create', '新增联系人 / 群', person && person.kind === 'person' ? person : null)
}

function openPerson(row) {
  openDialog('person', '联系人基本资料', row)
}

function openConversation(conversation) {
  openDialog('conversation', '会话设置 · ' + conversation.name, conversation)
}

function openPolicy(row, conversation = null) {
  openDialog('policy', conversation ? '会话角色与心跳' : '默认角色与 Skill', { row, conversation })
}

function openLink(row) {
  openDialog('link', '关联不同群昵称', row)
}

function openMembership(row) {
  openDialog('membership', '新增所属群', row)
}

function openSettings() {
  openDialog('settings', '全局监听设置')
}

function openBinding(member) {
  openDialog('binding', '编辑用户绑定', member)
}

function openNews() {
  section.value = 'subscriptions'
  loadNews()
}

function openAliases() {
  section.value = 'aliases'
  if (aliasDraft.value === null) initAliases()
}

function initAliases() {
  aliasDraft.value = (data.value?.aliases || []).map(row => ({ ...row }))
  aliasVersion.value = data.value?.version || 0
}

function setAliases(value) {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) aliasDraft.value = parsed
  } catch {
    // StructuredEditor 只在内容合法时提交，这里保持当前草稿。
  }
}

function cancelAliases() {
  error.value = ''
  initAliases()
}

function toggleNews(key, id, event) {
  if (!newsDraft.value) {
    newsVersion.value = news.value.version
    newsDraft.value = {
      categories: [...(news.value.settings.categories || [])],
      sources: [...(news.value.settings.sources || [])],
      count: news.value.settings.count
    }
  }
  const list = new Set(newsDraft.value[key])
  if (event.target.checked) list.add(id)
  else list.delete(id)
  newsDraft.value[key] = [...list]
  newsMessage.value = ''
  newsError.value = ''
}

function setNewsCount(event) {
  if (!newsDraft.value) {
    newsVersion.value = news.value.version
    newsDraft.value = {
      categories: [...(news.value.settings.categories || [])],
      sources: [...(news.value.settings.sources || [])],
      count: news.value.settings.count
    }
  }
  newsDraft.value.count = Number(event.target.value)
  newsMessage.value = ''
  newsError.value = ''
}

function showStatus(row) {
  loadStatus(row)
}
</script>

<template>
  <aside v-if="data?.active" id="list">
    <div class="user-filters">
      <h2>联系人 <small>{{ data.total }}</small></h2>
      <button id="contact-create" @click="openCreate()">新增联系人 / 群</button>
      <label>
        筛选
        <select id="contact-filter" v-model="kind">
          <option v-for="filter in FILTERS" :key="filter[0]" :value="filter[0]">{{ filter[1] }}</option>
        </select>
      </label>
      <button id="contact-news" @click="openNews">新闻推送设置</button>
      <button id="contact-settings" @click="openSettings">全局监听设置</button>
      <button id="contact-aliases" @click="openAliases">群昵称与待核对别名</button>
    </div>
    <button
      v-for="row in rows"
      :key="'c-' + row.id"
      class="user contact-row"
      :class="{ sel: current?.id === row.id }"
      @click="pick(row.id)"
    >
      <strong>{{ row.name }}</strong>
      <small>{{ rowNote(row) }}</small>
    </button>
  </aside>

  <section id="pane">
    <div v-if="!data" class="empty">{{ error || '正在读取联系人…' }}</div>

    <div v-else-if="!data.active" class="head">
      <h2>统一联系人尚未启用</h2>
      <p>先只读预览现有来源、同名联系人和目的地，核对后安排停机切换。</p>
      <pre>python -m butler contacts-preview</pre>
      <p>确认旧 Butler、log、wxbot 及订阅写入进程已经停止，再由安装者执行：</p>
      <pre>python -m butler contacts-migrate --acknowledge-stopped</pre>
      <p>切换会保留群昵称、停用状态、记忆及原投递目的地。此页面不会自动导入运行数据。</p>
      <a href="/app/?tab=configuration">查看当前配置来源</a>
    </div>

    <template v-else-if="section === 'subscriptions'">
      <div class="head">
        <h2>新闻推送设置</h2>
        <p>收件目的地在各联系人会话的订阅中维护。</p>
        <p class="warn">{{ error }}</p>
      </div>
      <div v-if="!news" class="news-settings">
        <p class="muted">新闻配置接口尚未加载，请手动重启 log 服务后刷新。</p>
      </div>
      <div v-else-if="news.error" class="news-settings">
        <p class="warn">{{ news.error }}</p>
      </div>
      <section v-else class="news-settings" aria-label="新闻推送设置">
        <div class="news-title"><h3>新闻推送设置</h3><span class="tag">{{ news.schedule }}</span></div>
        <p class="muted">{{ news.note }}</p>
        <fieldset :disabled="newsBusy">
          <legend>新闻类型 · 可多选</legend>
          <div class="news-choices">
            <label v-for="item in news.categories" :key="'nc-' + item.id" class="news-choice">
              <input
                type="checkbox"
                :value="item.id"
                :checked="newsValues.categories.includes(item.id)"
                :disabled="newsBusy"
                @change="toggleNews('categories', item.id, $event)"
              >
              <span>{{ item.label }}<small v-if="item.description">{{ item.description }}</small></span>
            </label>
          </div>
        </fieldset>
        <fieldset :disabled="newsBusy">
          <legend>新闻来源 · 可多选</legend>
          <div class="news-choices news-sources">
            <label v-for="item in news.sources" :key="'ns-' + item.id" class="news-choice">
              <input
                type="checkbox"
                :value="item.id"
                :checked="newsValues.sources.includes(item.id)"
                :disabled="newsBusy"
                @change="toggleNews('sources', item.id, $event)"
              >
              <span>{{ item.label }}<small v-if="item.description">{{ item.description }}</small></span>
            </label>
          </div>
          <p class="muted">首批来源为中新网官方 RSS 频道；重叠报道会去重，不足设定条数时按实际数量发送。</p>
        </fieldset>
        <div class="news-actions">
          <label for="news-count">每日新闻条数</label>
          <input
            id="news-count"
            type="number"
            min="1"
            max="10"
            step="1"
            :value="newsValues.count"
            :disabled="newsBusy"
            @input="setNewsCount"
          >
          <span class="muted">1～10 条；较长简报会分段发送</span>
        </div>
        <div class="news-actions">
          <button id="news-save" class="wx" :disabled="newsBusy" @click="saveNews">
            {{ newsBusy ? '保存中…' : '保存新闻设置' }}
          </button>
          <button id="news-cancel" :disabled="!newsDraft || newsBusy" @click="cancelNews">取消修改</button>
          <span class="news-feedback" role="status">{{ newsDraft ? '有未保存修改 · ' : '' }}{{ newsMessage }}</span>
        </div>
        <p id="news-error" class="warn" role="alert">{{ newsError }}</p>
        <div v-if="news.latest" class="news-last">
          最近执行：{{ news.latest.date }} · {{ NEWS_STATUS[news.latest.status] || news.latest.status }} ·
          新闻 {{ Number(news.latest.article_count) || 0 }} 条 · 已完成 {{ Number(news.latest.sent) || 0 }} 人
        </div>
        <p class="muted">保存后下次新闻任务生效，不会立即发送。</p>
      </section>
    </template>

    <template v-else-if="section === 'aliases'">
      <div class="head">
        <h2>群昵称与待核对别名</h2>
        <p>按群管理成员昵称，补充所属群后可取消待核对。修改显示昵称不会确认身份。</p>
        <p class="user-error" role="alert">{{ error }}</p>
      </div>
      <section class="contact-section">
        <StructuredEditor
          :model-value="aliasJson"
          widget="alias-list"
          :disabled="busy"
          @update:model-value="setAliases"
        />
        <div class="row">
          <button id="contact-alias-save" :disabled="busy" @click="saveAliases">保存群昵称</button>
          <button id="contact-alias-cancel" :disabled="busy" @click="cancelAliases">取消修改</button>
        </div>
      </section>
    </template>

    <template v-else-if="current">
      <div class="head">
        <h2>{{ current.name }} <span class="tag">{{ current.kind === 'group' ? '群聊' : '联系人' }}</span></h2>
        <img v-if="avatarOf(current)" class="user-avatar" :src="current.avatar" alt="联系人头像">
        <code>{{ current.id }}</code>
        <p v-if="current.historical_names?.length" class="muted">历史姓名：{{ current.historical_names.join('、') }}</p>
        <p>{{ current.enabled ? '已启用' : '已停用' }} · 版本 {{ data.version }}</p>
        <p class="user-error" role="alert">{{ error }}</p>
        <template v-if="personButtons(current)">
          <button id="contact-person-edit" @click="openPerson(current)">基本资料</button>
          <button id="contact-policy" @click="openPolicy(current)">默认角色与 Skill</button>
          <button id="contact-link" @click="openLink(current)">关联已有群成员</button>
          <button id="contact-membership" @click="openMembership(current)">新增所属群</button>
          <button id="contact-private" @click="openCreate(current)">新增私聊目的地</button>
        </template>
        <button id="contact-status" @click="showStatus(current)">心跳运行记录</button>
      </div>

      <section class="contact-section">
        <h3>会话与投递目的地</h3>
        <div v-for="conversation in current.conversations" :key="'cc-' + conversation.id" class="contact-conversation">
          <strong>{{ conversation.name }}</strong>
          <span class="tag">{{ conversation.channel_type === 'group' ? '群聊' : '私聊' }}</span>
          <p>
            {{ conversation.listening ? '监听开启' : '监听关闭' }} · {{ conversation.enabled ? '启用' : '停用' }} ·
            订阅 {{ subscriptionsText(conversation) }}
          </p>
          <button @click="openConversation(conversation)">监听 / 订阅 / 高级路由</button>
          <button @click="openPolicy(current, conversation)">会话角色与心跳</button>
          <button
            v-if="(conversation.policy || current.policy)?.role_skill"
            @click="triggerHeartbeat(conversation.name)"
          >立即触发一次心跳</button>
          <p class="muted">{{ policyText(current, conversation) }}{{ heartbeatOn(current, conversation) ? ' · 自动心跳开启' : '' }}</p>
        </div>
        <p v-if="!current.conversations.length">尚无私聊投递目的地；所在群中的昵称不会作为私聊窗口。</p>
      </section>

      <section class="contact-section">
        <h3>{{ current.kind === 'group' ? '群成员' : '所属群与群昵称' }}</h3>
        <p v-for="member in current.memberships" :key="'m-' + member.binding_id">
          <strong>{{ member.contact }}</strong> · {{ member.nickname }}{{ member.enabled ? '' : ' · 已停用' }}{{ member.identity_confirmed ? '' : ' · 待核对' }}
          <br>
          <code>{{ member.binding_id }}</code>
          <button v-if="current.kind === 'person'" @click="openBinding(member)">编辑群昵称 / 头像 / 状态</button>
          <button v-if="current.kind === 'group'" @click="pick(member.user_id)">打开联系人</button>
        </p>
        <p v-if="!current.memberships.length">暂无群成员关系。</p>
      </section>

      <section v-if="current.kind === 'person'" class="contact-section">
        <h3>共享记忆</h3>
        <p>{{ current.memory_count }} 条 · 各群保留自己的昵称与成员关系，个人记忆共用。</p>
        <button @click="loadMemory('person:' + current.id)">查看与整理共享记忆</button>
        <details v-if="current.memory_conflicts?.length">
          <summary>待整理记忆 · 保留全部来源</summary>
          <template v-for="item in current.memory_conflicts" :key="'mc-' + item.key + (item.source_label || '')">
            <p>{{ item.key }} · {{ item.source_label || item.source_user_id }}</p>
            <pre>{{ item.value }}</pre>
          </template>
        </details>
      </section>

      <HeartbeatStatus v-if="hbShown" />
    </template>

    <div v-else class="empty">没有匹配联系人。</div>
  </section>

  <ContactDialog v-if="dialog && isContactDialog" :key="dialogKey" />
  <UserDialog v-else-if="dialog" :key="dialogKey" />
</template>
