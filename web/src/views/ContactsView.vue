<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import {
  activeId, aliasDraft, aliasVersion, busy, contactRequest, data, dialog, error,
  hbShown, category, statusFilter, issueFilter, detailTab, load, loadMemory, loadStatus, openDialog, pick, query,
  saveAliases, section, triggerHeartbeat, openMerge
} from '../contactState'
import ContactDialog from '../components/ContactDialog.vue'
import ContactMergeDialog from '../components/ContactMergeDialog.vue'
import { STATUS_LABELS, contactStatus, pendingReasons, matchesContact, effectivePolicy, isPrivateContact } from '../contactPresentation'
import HeartbeatStatus from '../components/HeartbeatStatus.vue'
import StructuredEditor from '../components/StructuredEditor.vue'
import UserDialog from '../components/UserDialog.vue'

const ctx = inject('logWebCtx', null)

const SUBSCRIPTIONS = { 1: '新闻', 2: '问候', 3: '其他' }
const CATEGORIES = [['chats', '会话'], ['people', '私聊'], ['groups', '群聊'], ['pending', '待确认']]
const TABS = [['overview', '概览'], ['basic', '基本资料'], ['ai', 'AI 设置'], ['push', '主动消息'],
  ['groups', '群身份'], ['memory', '个人记忆'], ['maintenance', '身份管理']]
const ISSUES = ['窗口信息待补充', '身份待确认', '疑似重复档案', '记忆冲突', '缺少身份或窗口']
const rows = computed(() => (data.value?.rows || []).filter(row =>
  matchesContact(row, category.value, statusFilter.value, query.value, issueFilter.value)))
const listSections = computed(() => {
  return [
    { id: 'dm', title: '私聊', rows: rows.value.filter(isPrivateContact) },
    { id: 'group', title: '群聊', rows: rows.value.filter(row => row.kind === 'group') },
    { id: 'people', title: '群成员及其他档案', rows: rows.value.filter(row => row.kind === 'person' && !isPrivateContact(row)) }
  ].filter(item => item.rows.length)
})
function categoryCount(value) {
  return (data.value?.rows || []).filter(row => matchesContact(row, value, '', query.value)).length
}
function changeCategory(value) {
  memberContext.value = null
  category.value = value
  statusFilter.value = ''
  issueFilter.value = ''
  section.value = 'details'
}
function openIssue(row) {
  detailTab.value = row.memory_conflicts?.length ? 'memory' :
    row.merge_candidates?.length ? 'maintenance' : (!row.memberships.length || row.conversations?.some(c => c.needs_route)) ? 'basic' : 'groups'
}
const cleanupCandidates = computed(() => (data.value?.rows || []).filter(row => row.can_cleanup))
const memberContext = ref(null)
const current = computed(() => {
  const member = memberContext.value && data.value?.rows.find(row => row.id === memberContext.value.personId)
  if (member) return member
  const list = rows.value
  return list.find(row => row.id === activeId.value) || list[0] || null
})

const mergeTarget = ref('')

watch(() => current.value?.id, () => {
  const row = current.value
  mergeTarget.value = ''
  detailTab.value = 'overview'
  hbShown.value = false
  if (row && !memberContext.value && row.id !== activeId.value) activeId.value = row.id
}, { immediate: true })

watch([category, statusFilter, issueFilter, query], () => { memberContext.value = null })
watch(data, payload => {
  const context = memberContext.value
  if (context && !payload?.rows.some(row => row.id === context.personId)) memberContext.value = null
})

watch(() => ctx?.search?.contacts, value => { query.value = String(value || '') }, { immediate: true })

watch(() => ctx?.refreshKey?.value, () => load())

watch([data, section], () => {
  if (section.value === 'aliases' && aliasDraft.value === null && data.value?.active) initAliases()
})

const aliasJson = computed(() => JSON.stringify(aliasDraft.value || [], null, 2))
// 手动合并用的候选：疑似同人排在最前，其余按名称排列。
const mergePool = computed(() => {
  const suspected = new Set((current.value?.merge_candidates || []).map(item => item.id))
  return (data.value?.rows || [])
    .filter(row => row.kind === 'person' && row.id !== current.value?.id)
    .sort((a, b) => Number(suspected.has(b.id)) - Number(suspected.has(a.id)) || a.name.localeCompare(b.name))
})
// 弹窗按打开内容重建，保证表单一次性初始化。
const CONTACT_DIALOGS = ['create', 'profile', 'conversation', 'policy', 'relations', 'settings']
const isContactDialog = computed(() => CONTACT_DIALOGS.includes(dialog.value?.kind))
const dialogKey = computed(() => dialog.value
  ? dialog.value.kind + ':' + (dialog.value.payload?.id || dialog.value.payload?.row?.id || '')
  : 'none')

onMounted(load)

function avatarOf(row) {
  return /^data:image\/png;base64,/.test(row.avatar || '')
}

// 微信号就是微信主窗口里能搜到的会话名；群聊没有微信号，直接用群名。
function wechatOf(row) {
  if (row.wechat) return row.wechat
  return (row.conversations || []).find(item => item.channel_type === 'dm')?.name || ''
}

// 路由回答一个问题：bot 会不会读这个会话、能不能往这里发消息。
function routeText(row) { return STATUS_LABELS[contactStatus(row)] }

function rowNote(row) {
  const bits = [row.kind === 'group'
    ? (row.memberships.length ? row.memberships.length + ' 位成员' : '群聊')
    : (row.memberships.length
      ? row.memberships.length + ' 个所属群，共享记忆 ' + row.memory_count + ' 条'
      : '共享记忆 ' + row.memory_count + ' 条')]
  if (contactStatus(row) === 'disabled') bits.push('已停用')
  return bits.join('，')
}

function subscriptionsText(conversation) {
  return (conversation.subscriptions || []).map(value => SUBSCRIPTIONS[value] || '类型 ' + value).join('、') || '无'
}

function policyText(row, conversation) {
  const { policy, source } = effectivePolicy(row, conversation)
  return (policy?.role_skill || '未配置角色') + '，' + source
}
function heartbeatOn(row, conversation) { return Boolean(effectivePolicy(row, conversation).policy?.heartbeat_enabled) }
function allowedText(row, conversation) {
  return effectivePolicy(row, conversation).policy?.allowed_skills?.join('、') || '未授权额外功能'
}
function personButtons(row) {
  return row.kind === 'person' && (data.value?.rows || []).some(item => item.id === row.id) &&
    !row.conversations.some(item => item.id === row.id)
}

function initial(row) {
  return ((row && row.name) || '?').trim().slice(0, 1).toUpperCase()
}

function routeTag(row) {
  if (!row.enabled) return ['tag-off', '已停用']
  if (row.conversations.length && !row.conversations.some(item => item.enabled)) return ['tag-off', '会话停用']
  if (row.conversations.some(item => item.needs_route)) return ['tag-todo', '待补充']
  return null
}

function openCreate(person = null) {
  openDialog('create', '新增联系人 / 群', person && person.kind === 'person' ? person : null)
}

function openProfile(row) {
  openDialog('profile', '编辑联系人，' + row.name, row)
}

function openConversation(conversation) {
  openDialog('conversation', '会话设置，' + conversation.name, conversation)
}

function openPolicy(row, conversation = null) {
  openDialog('policy', conversation ? '会话角色与心跳' : '默认角色与 Skill', { row, conversation })
}

function openRelations(row) {
  openDialog('relations', '群成员关系，' + row.name, row)
}

function openSettings() {
  openDialog('settings', '全局监听设置')
}

function openBinding(member) {
  openDialog('binding', '编辑用户绑定', member)
}

function openMember(member) {
  const row = data.value?.rows.find(item => item.id === member.user_id)
  const group = current.value
  if (!row || group?.kind !== 'group') return
  memberContext.value = { personId: row.id, groupId: group.id, groupName: group.name }
  section.value = 'details'
  detailTab.value = 'overview'
  hbShown.value = false
}

function returnToGroup() {
  const groupId = memberContext.value?.groupId
  memberContext.value = null
  if (groupId) pick(groupId)
}

function selectContact(id) {
  memberContext.value = null
  pick(id)
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

function showStatus(row) {
  loadStatus(row)
}

const AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/webp']

function readAvatar(file) {
  if (!file) return Promise.resolve('')
  if (!AVATAR_TYPES.includes(file.type) || file.size > 512 * 1024) {
    return Promise.reject(new Error('头像须为 PNG、JPEG 或 WebP，最大 512 KiB'))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('头像读取失败'))
    reader.readAsDataURL(file)
  })
}

async function uploadAvatar(row, event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const avatar = await readAvatar(file)
    data.value = await contactRequest({ version: data.value.version, action: 'avatar', id: row.id, avatar })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    event.target.value = ''
  }
}

async function clearAvatar(row) {
  if (!window.confirm('清除「' + row.name + '」的全部头像？下次收到消息会重新采集。')) return
  try {
    data.value = await contactRequest({ version: data.value.version, action: 'avatar', id: row.id, avatar: '' })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  }
}

async function cleanupAvatars() {
  if (!window.confirm('清理全库可疑头像：1 KiB 以下的占位图，以及同一张图挂在别人名下的副本。不可撤销。')) return
  try {
    data.value = await contactRequest({ version: data.value.version, action: 'avatar_cleanup' })
    error.value = '已清理可疑头像'
  } catch (err) {
    error.value = err.message || String(err)
  }
}

async function disableBinding(row, member) {
  if (!window.confirm('停用「' + member.nickname + '」这条重复的群成员记录？身份和共享记忆保持不变。')) return
  try {
    data.value = await contactRequest({
      version: data.value.version, action: 'binding_disable', id: row.id, binding_id: member.binding_id
    })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  }
}

// 删掉一条重复的群身份；人物、其他身份和个人记忆会保留。
async function deleteBinding(row, member) {
  if (!window.confirm('删除「' + member.nickname + '」在「' + member.contact + '」的这条身份记录？\n仅移除这条身份及其识别证据；人物档案、聊天窗口和个人记忆保留。')) return
  try {
    data.value = await contactRequest({
      version: data.value.version, action: 'binding_delete', id: row.id, binding_id: member.binding_id
    })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  }
}

// 合并只把源档案的群身份、头像、记忆接到当前档案，源档案留在重定向表里供历史引用。
function mergePerson(row, item) { openMerge(item.id, row.id) }

async function mergeChosen(row) {
  const item = mergePool.value.find(candidate => candidate.id === mergeTarget.value)
  if (item) await mergePerson(row, item)
}

// 删除是彻底操作：联系人的投递窗口、群身份、头像和共享记忆一起消失，删完不可恢复。
async function deleteContact(row) {
  const routes = (row.conversations || []).length
  const message = row.kind === 'group'
    ? '从列表移除群「' + row.name + '」？\n只摘掉它的监听与订阅路由，群成员档案和群昵称记录都会保留，随时可以重新添加。'
    : '删除联系人「' + row.name + '」？\n它的 ' + routes + ' 个投递窗口、' + (row.bindings?.length || 0) + ' 条群身份、头像和 '
      + (row.memory_count || 0) + ' 条共享记忆都会消失，此操作不可撤销。'
  if (!window.confirm(message)) return
  try {
    data.value = await contactRequest({ version: data.value.version, action: 'contact_delete', id: row.id, kind: row.kind })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  }
}

async function cleanupPending() {
  if (!window.confirm('删除全部以「待命名-」开头、且从未确认过的档案？\n它们的群成员关系、头像和共享记忆都会消失，此操作不可撤销。')) return
  try {
    data.value = await contactRequest({ version: data.value.version, action: 'person_cleanup',
      ids: cleanupCandidates.value.map(row => row.id) })
    error.value = ''
  } catch (err) {
    error.value = err.message || String(err)
  }
}
</script>

<template>
  <aside v-if="data?.active" id="list">
    <div class="contact-tools">
      <div class="contact-tools-title"><h2>联系人 <small>{{ rows.length }}</small></h2>
        <button id="contact-create" class="wx" @click="openCreate()">新增联系人 / 群</button></div>
      <nav class="contact-tabs" aria-label="联系人分类">
        <button v-for="[value, label] in CATEGORIES" :key="value" :data-category="value"
          :aria-pressed="category === value" @click="changeCategory(value)">{{ label }} {{ categoryCount(value) }}</button>
      </nav>
      <label class="contact-filter"><span>状态</span>
        <select id="contact-filter" v-model="statusFilter"><option value="">全部状态</option>
          <option v-for="(label, value) in STATUS_LABELS" :key="value" :value="value">{{ label }}</option></select></label>
      <label v-if="category === 'pending'" class="contact-filter"><span>问题</span>
        <select id="contact-issue-filter" v-model="issueFilter"><option value="">全部问题</option>
          <option v-for="issue in ISSUES" :key="issue">{{ issue }}</option></select></label>
      <input class="contact-search" v-model="query" type="search" placeholder="搜索姓名、窗口或群昵称" aria-label="搜索联系人">
      <details class="contact-tools-more"><summary>全局设置</summary><div class="contact-tools-body">
        <button id="contact-settings" @click="openSettings">全局监听设置</button>
        <button id="contact-aliases" @click="openAliases">群昵称与待核对别名</button>
      </div></details>
    </div>
    <section v-for="group in listSections" :key="group.id" class="contact-list-section"
      :data-contact-section="group.id" :aria-labelledby="'contact-section-' + group.id">
      <h3 :id="'contact-section-' + group.id">{{ group.title }} <span>{{ group.rows.length }}</span></h3>
      <div class="contact-table-head" aria-hidden="true"><span>头像</span><span>名称 / 角色</span><span>微信窗口名称</span><span>收发状态</span></div>
      <button v-for="row in group.rows" :key="row.id" class="user contact-row"
        :class="{ sel: (memberContext?.groupId || current?.id) === row.id }" @click="selectContact(row.id)">
        <span class="contact-cell contact-cell-avatar"><img v-if="avatarOf(row)" class="contact-thumb" :src="row.avatar" :alt="row.name + ' 的头像'">
          <span v-else class="contact-avatar" :class="{ 'is-group': row.kind === 'group' }">{{ initial(row) }}</span></span>
        <span class="contact-cell contact-cell-name"><strong>{{ row.name }}</strong><small>{{ rowNote(row) }}</small>
          <small>{{ row.kind === 'group' ? '群聊' : '联系人' }}，{{ policyText(row, row.conversations[0]) }}</small></span>
        <span class="contact-cell contact-cell-wechat">{{ row.kind === 'group' ? row.name : wechatOf(row) || '未配置私聊' }}</span>
        <span class="contact-cell contact-cell-route">{{ routeText(row) }}</span>
      </button>
    </section>
    <p v-if="!rows.length" class="empty">没有匹配结果，可调整分类、状态或搜索词。</p>
  </aside>
  <section id="pane">
    <div v-if="!data" class="empty">{{ error || '正在读取联系人…' }}</div>
    <div v-else-if="!data.active" class="head"><h2>统一联系人尚未启用</h2>
      <p>先只读预览现有资料，核对后由安装者安排切换。</p><pre>python -m butler contacts-preview</pre>
      <p>停止旧 Butler、管理台、wxbot 和其他写入进程后，再由安装者执行：</p>
      <pre>python -m butler contacts-migrate --acknowledge-stopped</pre></div>
    <template v-else-if="section === 'aliases'">
      <div class="head"><h2>群昵称与待核对别名</h2><p>修改昵称不会自动确认身份。</p><p class="user-error" role="alert">{{ error }}</p></div>
      <section class="contact-section"><StructuredEditor :model-value="aliasJson" widget="alias-list" :disabled="busy" @update:model-value="setAliases" />
        <button id="contact-alias-save" :disabled="busy" @click="saveAliases">保存群昵称</button>
        <button id="contact-alias-cancel" :disabled="busy" @click="cancelAliases">取消修改</button>
        <button @click="section = 'details'">返回详情</button></section>
    </template>
    <template v-else-if="current">
      <div class="head contact-head">
        <button v-if="memberContext" id="contact-member-back" :title="memberContext.groupName"
          :aria-label="'返回群聊：' + memberContext.groupName" @click="returnToGroup">返回群聊</button>
        <div class="contact-head-row"><div class="contact-head-avatar">
          <img v-if="avatarOf(current)" class="user-avatar user-avatar-lg" :src="current.avatar" :alt="current.name + ' 的头像'">
          <span v-else class="contact-avatar contact-avatar-lg">{{ initial(current) }}</span>
        </div><div class="contact-head-main"><h2>{{ current.name }} <span class="tag">{{ current.kind === 'group' ? '群聊' : '联系人' }}</span></h2>
          <p>{{ routeText(current) }}，{{ current.conversations.length }} 个聊天窗口，{{ current.memberships.length }} {{ current.kind === 'group' ? '位成员' : '个所属群' }}</p></div></div>
        <div class="contact-head-actions">
          <button id="contact-delete" type="button" class="danger" @click="deleteContact(current)">{{ current.kind === 'group' ? '移除群聊' : '删除联系人' }}</button>
        </div>
        <p class="user-error" role="alert">{{ error }}</p>
        <nav class="contact-tabs contact-detail-tabs" aria-label="联系人详情分区">
          <template v-for="[value, label] in TABS" :key="value"><button v-if="current.kind === 'person' || value !== 'memory'" :data-detail="value"
            :aria-pressed="detailTab === value" @click="detailTab = value; hbShown = false">{{ value === 'groups' && current.kind === 'group' ? '群成员' : label }}</button></template>
        </nav>
      </div>
      <section v-if="detailTab === 'overview'" class="contact-section">
        <h3>概览</h3><p>微信窗口名称：{{ current.kind === 'group' ? current.name : wechatOf(current) || '未配置私聊' }}</p>
        <p v-if="!current.conversations.length">仅有群身份也能保留个人记忆，无需为每位群成员创建私聊。</p>
        <p v-for="conversation in current.conversations" :key="conversation.id">{{ conversation.name }}：{{ policyText(current, conversation) }}</p>
        <p v-if="current.kind === 'person'">个人记忆：{{ current.memory_count }} 条</p>
        <div class="row"><button @click="detailTab = 'basic'">配置收发</button><button @click="detailTab = 'ai'">设置 AI 角色</button></div>
        <div v-if="pendingReasons(current).length" class="contact-notice"><strong>待确认事项</strong>
          <p>{{ pendingReasons(current).join('、') }}</p><button @click="openIssue(current)">查看并处理</button></div>
      </section>
      <section v-else-if="detailTab === 'basic'" class="contact-section">
        <h3>基本资料</h3><p>显示名与微信窗口名称分别维护，修改姓名不会合并人物。</p>
        <div v-if="personButtons(current)" class="row"><button id="contact-person-edit" @click="openProfile(current)">编辑资料</button>
          <button id="contact-private" @click="openCreate(current)">新增私聊窗口</button>
          <label class="contact-avatar-edit">更换头像<input type="file" accept="image/png,image/jpeg,image/webp" @change="uploadAvatar(current, $event)"></label>
          <button v-if="avatarOf(current)" @click="clearAvatar(current)">清除头像</button></div>
        <article v-for="conversation in current.conversations" :key="conversation.id" class="contact-card">
          <h3>{{ conversation.name }}</h3><p>{{ conversation.enabled ? '窗口启用' : '窗口停用' }}，{{ conversation.listening ? '监听开启' : '监听关闭' }}</p>
          <button @click="openConversation(conversation)">编辑窗口与收发设置</button></article>
      </section>
      <section v-else-if="detailTab === 'ai'" class="contact-section">
        <h3>AI 设置</h3>
        <template v-if="personButtons(current)"><p>默认角色：{{ current.policy?.role_skill || '未配置' }}</p>
          <p class="muted">默认角色是这个人的 AI 人设和工具白名单，他所有会话共用；某个窗口单独设了角色就以窗口为准。</p>
          <button @click="openPolicy(current)">设置默认角色与允许功能</button></template>
        <article v-for="conversation in current.conversations" :key="conversation.id" class="contact-card">
          <h3>{{ conversation.name }}</h3><p>{{ policyText(current, conversation) }}</p>
          <p>允许功能：{{ allowedText(current, conversation) }}</p><button @click="openPolicy(current, conversation)">设置此窗口角色与功能</button></article>
        <p class="muted">角色与功能保存后对后续请求生效；此处展示配置结果。</p>
      </section>
      <section v-else-if="detailTab === 'push'" class="contact-section">
        <h3>主动消息</h3><p>订阅和主动问候都发送到对应窗口。</p>
        <div v-if="!current.conversations.length"><p>尚未配置私聊发送窗口。</p><button @click="openCreate(current)">配置发送窗口</button></div>
        <article v-for="conversation in current.conversations" :key="conversation.id" class="contact-card">
          <h3>发送窗口：{{ conversation.name }}</h3><p>{{ conversation.enabled ? '窗口启用' : '窗口停用' }}</p>
          <p>订阅：{{ subscriptionsText(conversation) }}</p><p>自动问候：{{ heartbeatOn(current, conversation) ? '开启' : '关闭' }}</p>
          <div class="row"><button @click="openConversation(conversation)">设置订阅</button>
            <button @click="openPolicy(current, conversation)">设置主动问候</button>
            <button v-if="conversation.enabled && effectivePolicy(current, conversation).policy?.role_skill" @click="triggerHeartbeat(conversation.name)">立即触发一次问候</button>
            <button @click="showStatus({ conversations: [conversation] })">查看此窗口运行记录</button></div></article>
        <HeartbeatStatus v-if="hbShown" />
      </section>
      <section v-else-if="detailTab === 'groups'" class="contact-section">
        <h3>{{ current.kind === 'group' ? '群成员' : '所属群与群昵称' }} <small>{{ current.memberships.length }}</small></h3>
        <button v-if="personButtons(current)" id="contact-relations" @click="openRelations(current)">管理群成员关系</button>
        <p v-if="current.hidden_memberships" class="muted">同一人物的 {{ current.hidden_memberships }} 条重复绑定已折叠；不同人物的同昵称记录仍分别显示。</p>
        <p v-for="member in current.memberships" :key="member.binding_id" class="contact-member">
          <span><strong>{{ member.nickname }}</strong>，{{ member.contact }} <span class="tag">{{ member.identity_confirmed ? '已确认' : '待确认身份' }}</span>
            <small v-if="!member.enabled">，已停用</small></span>
          <span class="contact-member-actions"><template v-if="current.kind === 'person'">
            <button @click="openBinding(member)">编辑群身份</button><button @click="deleteBinding(current, member)">移除这条身份</button></template>
            <button v-else @click="openMember(member)">查看成员资料</button></span></p>
        <p v-if="!current.memberships.length">暂无群成员关系。</p>
        <details v-if="current.hidden_memberships && current.kind === 'person'"><summary>查看全部群绑定</summary>
          <p v-for="binding in current.bindings.filter(item => item.channel_type === 'group')" :key="binding.binding_id">{{ binding.contact }}，{{ binding.nickname }}
            <button @click="openBinding(binding)">编辑</button><button @click="deleteBinding(current, binding)">移除身份</button></p></details>
      </section>
      <section v-else-if="detailTab === 'memory' && current.kind === 'person'" class="contact-section">
        <h3>个人记忆 <small>{{ current.memory_count }} 条</small></h3><p>已确认关联到此人的群身份共用个人记忆，各群保留自己的昵称。</p>
        <button @click="loadMemory('person:' + current.id)">查看与整理个人记忆</button>
        <details v-if="current.memory_conflicts?.length"><summary>待整理记忆，保留全部来源</summary>
          <p v-for="(item, index) in current.memory_conflicts" :key="index">{{ item.key }}：{{ item.value }}（{{ item.source_label || item.source_user_id }}）</p></details>
      </section>
      <section v-else-if="detailTab === 'maintenance'" class="contact-section">
        <h3>身份管理</h3><p>只有确认属于同一个人后才合并，重名和相似头像都只是候选线索。</p>
        <template v-if="current.kind === 'person'">
          <p v-for="item in current.merge_candidates || []" :key="item.id">疑似重复：{{ item.name }}，{{ item.contact }}
            <button @click="mergePerson(current, item)">预览合并影响</button></p>
          <div class="row"><select v-model="mergeTarget" aria-label="选择并入来源"><option value="">选择要并入的档案…</option>
            <option v-for="row in mergePool" :key="row.id" :value="row.id">{{ row.name }}，{{ wechatOf(row) || row.id }}</option></select>
            <button :disabled="!mergeTarget" @click="mergeChosen(current)">预览并入当前人物</button></div>
        </template>
        <details class="contact-maintenance"><summary>技术信息</summary>
          <p>固定 ID：<code>{{ current.id }}</code>，版本 {{ data.version }}</p>
          <p v-if="current.historical_names?.length">历史名称：{{ current.historical_names.join('、') }}</p>
          <p v-if="current.kind === 'person'">永久删除将清理该人物的全部身份、私聊窗口和个人记忆。仅移除群关系请到“群身份”。</p>
        </details>
        <details class="contact-maintenance"><summary>全局维护工具</summary>
          <p>清理工具作用于全部档案，服务端会再次检查是否有已确认身份、窗口或记忆。</p>
          <button id="contact-avatar-cleanup" @click="cleanupAvatars">清理可疑头像</button>
          <details><summary>预览未命名空档案候选（{{ cleanupCandidates.length }}）</summary>
            <p v-for="row in cleanupCandidates" :key="row.id">{{ row.name }}，{{ row.bindings?.length || 0 }} 条未确认身份，无窗口和个人记忆</p>
            <button id="contact-pending-cleanup" :disabled="!cleanupCandidates.length" @click="cleanupPending">清理符合条件的未命名空档案</button>
          </details>
        </details>
      </section>
    </template>
    <div v-else class="empty">没有匹配联系人。</div>
  </section>
  <ContactMergeDialog v-if="dialog?.kind === 'merge'" :key="dialogKey" />
  <ContactDialog v-else-if="dialog && isContactDialog" :key="dialogKey" />
  <UserDialog v-else-if="dialog" :key="dialogKey" />
</template>
