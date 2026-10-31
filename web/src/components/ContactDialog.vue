<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  closeDialog, contactSave, data, dialog, dialogBusy, dialogError, openMerge, submitDialog
} from '../contactState'

const shell = ref(null)
const loading = ref(false)
const loaded = ref(false)
const skills = ref([])
const payload = dialog.value.payload
const mode = dialog.value.kind
const form = reactive({
  name: '',
  channel: 'dm',
  enabled: false,
  merge: false,
  listening: false,
  subscriptions: [],
  uid: '',
  profile: '',
  label: '',
  session_key: '',
  role: '',
  allowed: [],
  heartbeat: false,
  binding: '',
  ack: false,
  group: '',
  nickname: '',
  mentions: '',
  listenAll: false
})

onMounted(() => {
  const node = shell.value
  if (!node) return
  if (typeof node.showModal === 'function') {
    try {
      node.showModal()
    } catch {
      node.setAttribute('open', '')
    }
  } else {
    node.setAttribute('open', '')
  }
  init()
})

function init() {
  if (mode === 'create') {
    form.name = payload?.name || ''
  } else if (mode === 'profile') {
    form.name = payload.name || ''
    form.enabled = Boolean(payload.enabled)
  } else if (mode === 'conversation') {
    form.name = payload.name || ''
    form.enabled = Boolean(payload.enabled)
    form.listening = Boolean(payload.listening)
    form.subscriptions = [...(payload.subscriptions || [])]
    form.uid = payload.uid || ''
    form.profile = payload.profile || ''
    form.label = payload.label || ''
    form.session_key = payload.session_key || ''
  } else if (mode === 'policy') {
    loadPolicy()
  } else if (mode === 'relations') {
    form.group = groups()[0]?.id || ''
  } else if (mode === 'settings') {
    const settings = data.value?.settings || {}
    form.mentions = ((settings.bot || {}).mention_names || []).join('\n')
    form.listenAll = Boolean(((settings.wechat || {}).main_window || {}).listen_all)
  }
}

function isRoleSkill(skill) {
  return (Array.isArray(skill.tags) ? skill.tags : [])
    .some(tag => String(tag).trim().toLowerCase() === 'butler-role')
}

async function loadPolicy() {
  loading.value = true
  try {
    const conversation = payload.conversation || null
    const row = payload.row || payload
    const query = conversation
      ? new URLSearchParams({ contact: conversation.name })
      : new URLSearchParams({ id: row.id })
    const controller = new AbortController()
    // 服务端要连 Butler 取技能清单；连不上时最多等 12 秒，不能让弹窗一直停在加载中。
    const timer = setTimeout(() => controller.abort(), 12000)
    const response = await fetch('/api/skills?' + query, {
      headers: { Accept: 'application/json' },
      signal: controller.signal
    }).finally(() => clearTimeout(timer))
    const text = await response.text()
    const result = text ? JSON.parse(text) : {}
    if (!response.ok) throw new Error(result.detail || result.error || 'Skill 目录读取失败')
    skills.value = result.skills || []
    loaded.value = true
    const policy = (conversation ? conversation.policy : row.policy) ||
      { role_skill: '', allowed_skills: [], heartbeat_enabled: false }
    form.role = policy.role_skill || ''
    form.allowed = [...(policy.allowed_skills || [])]
    form.heartbeat = Boolean(policy.heartbeat_enabled)
  } catch (err) {
    dialogError.value = (err.name === 'TimeoutError' || err.name === 'AbortError')
      ? 'Skill 目录读取超时，Butler 服务可能没有启动；重试仍失败就先检查服务再回来设置。'
      : err.message || String(err)
  } finally {
    loading.value = false
  }
}

function roleSkills() {
  return skills.value.filter(isRoleSkill)
}

function toolSkills() {
  return skills.value.filter(skill => !isRoleSkill(skill))
}

function groups() {
  return (data.value?.rows || []).filter(row => row.kind === 'group')
}

function candidates() {
  if (!payload) return []
  return (data.value?.rows || [])
    .filter(row => row.kind === 'person' && row.id !== payload.id)
    .flatMap(row => (row.memberships || []).map(member => ({
      ...member, person: row.name, memory_count: row.memory_count
    })))
}

function subscriptionChoices(conversation) {
  return [...new Set([1, 2, 3, ...(conversation.subscriptions || [])])]
}

function subscriptionLabel(value) {
  return { 1: '新闻', 2: '问候', 3: '其他' }[value] || '类型 ' + value
}

function onRoleChange() {
  form.allowed = form.allowed.filter(name => name !== form.role)
}

function onSubscription(value, event) {
  const set = new Set(form.subscriptions)
  if (event.target.checked) set.add(value)
  else set.delete(value)
  form.subscriptions = [...set]
}

function submitCreate() {
  submitDialog(async () => {
    await contactSave({
      action: 'create',
      name: form.name,
      channel_type: form.channel,
      ...(payload ? { person_id: payload.id } : {})
    })
  })
}

function submitProfile() {
  submitDialog(async () => {
    const body = { action: 'person', id: payload.id, name: form.name }
    if (form.enabled !== Boolean(payload.enabled)) body.enabled = form.enabled
    await contactSave(body)
  })
}

function submitConversation() {
  submitDialog(async () => {
    await contactSave({
      action: 'conversation',
      id: payload.id,
      name: form.name,
      enabled: form.enabled,
      listening: form.listening,
      subscriptions: form.subscriptions,
      uid: form.uid,
      profile: form.profile,
      label: form.label,
      session_key: form.session_key
    })
  })
}

function submitPolicy() {
  submitDialog(async () => {
    const policy = form.role
      ? { role_skill: form.role, allowed_skills: form.allowed, heartbeat_enabled: form.heartbeat }
      : null
    const conversation = payload.conversation
    await contactSave({
      action: conversation ? 'conversation' : 'person',
      id: conversation ? conversation.id : payload.row.id,
      policy
    })
  })
}

function submitLink() {
  const member = candidates().find(item => item.binding_id === form.binding)
  if (!member) {
    dialogError.value = '请选择要关联的群成员'
    return
  }
  openMerge(member.user_id, payload.id)
}

function submitMembership() {
  submitDialog(async () => {
    await contactSave({
      action: 'membership',
      id: payload.id,
      group_id: form.group,
      nickname: form.nickname
    })
  })
}

function submitSettings() {
  submitDialog(async () => {
    await contactSave({
      action: 'settings',
      settings: {
        bot: { mention_names: form.mentions.split('\n').map(value => value.trim()).filter(Boolean) },
        wechat: { main_window: { listen_all: form.listenAll } }
      }
    })
  })
}
</script>

<template>
  <Teleport to="body">
    <dialog id="user-dialog" ref="shell" class="user-dialog" @cancel.prevent="closeDialog">
      <div class="user-dialog-title">
        <h2>{{ dialog.title }}</h2>
        <button type="button" id="user-dialog-close" aria-label="关闭" @click="closeDialog">关闭</button>
      </div>
      <p id="user-dialog-error" class="user-error" role="alert">{{ dialogError }}</p>
      <div id="user-dialog-content">
        <p v-if="mode === 'policy' && loading">读取服务端 Skill 目录…</p>

        <form v-else-if="mode === 'create'" id="contact-create-form" class="user-form" @submit.prevent="submitCreate">
          <label>微信窗口名称<input v-model="form.name" name="name" required maxlength="200"></label>
          <label>
            类型
            <select v-model="form.channel" name="channel">
              <option value="dm">私聊</option>
              <option v-if="!payload" value="group">群聊</option>
            </select>
          </label>
          <p>新增后监听与主动问候默认关闭。在详情中选择角色及订阅。</p>
          <button type="submit" :disabled="dialogBusy">创建</button>
        </form>

        <form v-else-if="mode === 'profile'" id="contact-profile-form" class="user-form" @submit.prevent="submitProfile">
          <label>人物显示名<input v-model="form.name" name="name" required></label>
          <p>只修改显示名，不修改微信窗口或群昵称；重名不会合并人物。</p>
          <p v-if="data.rows.some(row => row.id !== payload.id && row.name === form.name)">已有同名档案，请用窗口和群身份区分。</p>
          <label class="user-check"><input v-model="form.enabled" name="enabled" type="checkbox">启用此人的全部身份与私聊窗口</label>
          <button type="submit" :disabled="dialogBusy">保存基本资料</button>
        </form>

        <form v-else-if="mode === 'conversation'" id="contact-conversation-form" class="user-form" @submit.prevent="submitConversation">
          <label>微信窗口名称<input v-model="form.name" name="name" required></label>
          <p>用于在微信主窗口定位聊天：微信主窗口里能搜到的会话名，bot 靠它把消息投递到这个窗口。改错会导致发不出去。</p>
          <div class="user-check-row">
            <label class="user-check"><input v-model="form.enabled" name="enabled" type="checkbox">启用此目的地</label>
            <label class="user-check"><input v-model="form.listening" name="listening" type="checkbox">监听此会话</label>
          </div>
          <fieldset>
            <legend>订阅，投递到此窗口</legend>
            <label v-for="value in subscriptionChoices(payload)" :key="'sub-' + value">
              <input
                type="checkbox"
                name="subscription"
                :value="value"
                :checked="form.subscriptions.includes(value)"
                @change="onSubscription(value, $event)"
              >{{ subscriptionLabel(value) }}
            </label>
          </fieldset>
          <details>
            <summary>高级收发设置，保留兼容设置</summary>
            <label>uid<input v-model="form.uid" name="uid"></label>
            <label>profile<input v-model="form.profile" name="profile"></label>
            <label>label<input v-model="form.label" name="label"></label>
            <label>session_key<input v-model="form.session_key" name="session_key"></label>
          </details>
          <button type="submit" :disabled="dialogBusy">保存会话</button>
        </form>

        <form v-else-if="mode === 'policy'" id="contact-policy-form" class="user-form" @submit.prevent="submitPolicy">
          <label>
            AI 角色
            <select v-model="form.role" name="role" @change="onRoleChange">
              <option value="">
                {{ payload.conversation ? '使用联系人默认角色 / 取消会话覆盖' : '不绑定默认角色' }}
              </option>
              <option v-for="skill in roleSkills()" :key="'role-' + skill.name" :value="skill.name">{{ skill.name }}</option>
            </select>
          </label>
          <fieldset>
            <legend>允许的功能</legend>
            <label v-for="skill in toolSkills()" :key="'tool-' + skill.name" class="user-skill">
              <input v-model="form.allowed" type="checkbox" name="skill" :value="skill.name">
              <span>{{ skill.name }}<small>{{ skill.description || '' }}</small></span>
            </label>
          </fieldset>
          <label class="user-check"><input v-model="form.heartbeat" name="heartbeat" type="checkbox">自动问候</label>
          <p>{{ payload.conversation ? '主动问候与订阅继续投递到此窗口。' : '个人主动问候必须配置明确的私聊目的地。' }}保存角色和 Skill 后后续请求生效。</p>
          <p v-if="!loading && !loaded" class="user-hint">技能目录没读出来，此时保存会把角色清空；先处理好上面的错误再回来。</p>
          <button type="submit" :disabled="dialogBusy || !loaded">保存策略</button>
        </form>

        <div v-else-if="mode === 'relations'" class="user-form">
          <form id="contact-link-form" class="user-form user-section" @submit.prevent="submitLink">
            <h3>关联已有群成员</h3>
            <label>
              已有群成员
              <select v-model="form.binding" name="binding" required>
                <option value="">选择已核对的成员</option>
                <option v-for="member in candidates()" :key="'cand-' + member.binding_id" :value="member.binding_id">
                  {{ member.person }}，{{ member.contact }}－{{ member.nickname }}，{{ member.memory_count }} 条记忆{{ member.enabled ? '' : '，已停用' }}
                </option>
              </select>
            </label>
            <p>所选成员及同一固定用户的全部关系归并到「{{ payload.name }}」。保留各群昵称与停用开关，双方个人记忆全部共享；同 key 的不同内容保留来源，进入待整理记忆。</p>
            <label class="user-check"><input v-model="form.ack" name="ack" type="checkbox" required>我已核对成员身份，继续查看合并范围</label>
            <button type="submit" :disabled="dialogBusy">预览身份合并</button>
          </form>
          <form id="contact-membership-form" class="user-form user-section" @submit.prevent="submitMembership">
            <h3>新增所属群</h3>
            <label>
              所属群
              <select v-model="form.group" name="group" required>
                <option v-for="group in groups()" :key="'g-' + group.id" :value="group.id">{{ group.name }}</option>
              </select>
            </label>
            <label>此人在该群的昵称<input v-model="form.nickname" name="nickname" required></label>
            <p>此操作明确确认身份，并将成员关系关联到当前联系人的共享记忆。</p>
            <label class="user-check"><input type="checkbox" required>已核对群成员身份</label>
            <button type="submit" :disabled="dialogBusy">保存所属群</button>
          </form>
        </div>

        <form v-else-if="mode === 'settings'" id="contact-settings-form" class="user-form" @submit.prevent="submitSettings">
          <label>机器人群昵称（每行一个）<textarea v-model="form.mentions" name="mentions"></textarea></label>
          <label class="user-check"><input v-model="form.listenAll" name="all" type="checkbox">监听所有会话</label>
          <p>具体会话监听开关在联系人详情维护。群昵称只用于判断 @，不会授予身份或工具权限。</p>
          <button type="submit" :disabled="dialogBusy">保存</button>
        </form>
      </div>
    </dialog>
  </Teleport>
</template>
