<script setup>
import { onMounted, reactive, ref } from 'vue'
import {
  closeDialog, contactRequest, contactSave, data, dialog, dialogBusy, dialogError, error, openMerge, submitDialog
} from '../contactState'

const shell = ref(null)
const loading = ref(false)
const loaded = ref(false)
const skills = ref([])
const unavailableSkills = ref([])
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
  listenAll: false,
  voiceMode: 'off',
  voiceAssetId: '',
  indexTtsEnabled: false,
  webuiPreset: ''
})
const voiceAssets = ref([])
const voiceEnabled = ref(false)
const voiceLoading = ref(false)
const voiceLoaded = ref(false)
const voiceError = ref('')
const initialVoice = { contact: '', mode: 'off', assetId: '' }
const ttsLoading = ref(false)
const ttsLoaded = ref(false)
const ttsAvailable = ref(false)
const ttsError = ref('')
let ttsPolicy = null
let initialTtsEnabled = false
const webPresets = ref([])
const webPresetLoading = ref(false)
const webPresetLoaded = ref(false)
const webPresetError = ref('')
const initialWebPreset = { contact: '', preset: '', version: '' }

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
    form.voiceMode = 'off'
    form.voiceAssetId = ''
    loadVoiceBinding(form.name)
    const policy = payload.policy || payload.effectivePolicy
    ttsPolicy = policy ? { ...policy, allowed_skills: [...(policy.allowed_skills || [])] } : null
    initialTtsEnabled = Boolean(ttsPolicy?.allowed_skills.includes('index-tts'))
    form.indexTtsEnabled = initialTtsEnabled
    loadTtsCatalogue()
    loadWebPresets(payload.name)
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
    const installed = new Set(toolSkills().map(skill => skill.name))
    unavailableSkills.value = [...new Set(form.allowed.filter(name => !installed.has(name)))]
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

async function loadTtsCatalogue() {
  ttsLoading.value = true
  ttsLoaded.value = false
  ttsError.value = ''
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 12000)
  try {
    const response = await fetch('/api/skills?' + new URLSearchParams({ contact: payload.name }), {
      headers: { Accept: 'application/json' }, signal: controller.signal
    })
    const result = JSON.parse(await response.text() || '{}')
    if (!response.ok) throw new Error(result.error || '技能目录读取失败')
    ttsAvailable.value = (result.skills || []).some(skill => skill.name === 'index-tts' && !isRoleSkill(skill))
    ttsLoaded.value = true
  } catch (err) {
    ttsError.value = err.name === 'AbortError' ? '读取技能超时，请检查 Butler 连接后重试。' : err.message || String(err)
  } finally {
    clearTimeout(timer)
    ttsLoading.value = false
  }
}

async function loadWebPresets(contactName) {
  webPresetLoading.value = true
  webPresetError.value = ''
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 12000)
  try {
    const response = await fetch('/api/tts-presets?' + new URLSearchParams({ contact: contactName }), {
      headers: { Accept: 'application/json' }, signal: controller.signal
    })
    const result = JSON.parse(await response.text() || '{}')
    if (response.status === 404) throw new Error('管理台尚未加载网页预设接口，请手动重启管理台后刷新。')
    if (!response.ok || result.ok !== true || typeof result.version !== 'string' || typeof result.preset !== 'string') {
      throw new Error(result.error || '网页预设读取失败')
    }
    webPresets.value = Array.isArray(result.presets) ? result.presets : []
    form.webuiPreset = result.preset
    Object.assign(initialWebPreset, { contact: contactName, preset: result.preset, version: result.version })
    webPresetLoaded.value = true
    webPresetError.value = result.available ? '' : result.error || '网页预设暂不可读，已保留当前绑定。'
  } catch (err) {
    webPresetError.value = err.name === 'AbortError' ? '网页预设读取超时，请检查 IndexTTS 网页后重试。' : err.message || String(err)
  } finally {
    clearTimeout(timer)
    webPresetLoading.value = false
  }
}

async function saveWebPreset(contactName, preset) {
  if (!webPresetLoaded.value ||
      (contactName === initialWebPreset.contact && preset === initialWebPreset.preset)) return
  const response = await fetch('/api/tts-presets', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Wxbot-TTS-Action': '1' },
    body: JSON.stringify({ contact: contactName, preset, version: initialWebPreset.version })
  })
  const result = JSON.parse(await response.text() || '{}')
  if (!response.ok || result.ok !== true || typeof result.version !== 'string' || result.preset !== preset) {
    throw new Error(result.error || '网页预设绑定未确认')
  }
  Object.assign(initialWebPreset, { contact: contactName, preset: result.preset, version: result.version })
}

function groups() {
  return (data.value?.rows || []).filter(row => row.kind === 'group')
}

function candidates() {
  if (!payload) return []
  return (data.value?.rows || [])
    .filter(row => row.kind === 'person' && row.id !== payload.id)
    .flatMap(row => (row.memberships || []).map(member => ({
      ...member, person: row.name
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

async function loadVoiceBinding(contactName) {
  voiceLoading.value = true
  voiceLoaded.value = false
  voiceError.value = ''
  try {
    const response = await fetch('/api/voice-bindings', { headers: { Accept: 'application/json' } })
    const text = await response.text()
    const result = text ? JSON.parse(text) : {}
    if (!response.ok) throw new Error(result.error || '读取音色绑定失败')
    voiceAssets.value = result.assets || []
    voiceEnabled.value = Boolean(result.enabled)
    const key = String(contactName || '').trim()
    form.voiceMode = (result.contacts && result.contacts[key]) || 'off'
    form.voiceAssetId = (result.contact_refs && result.contact_refs[key] && result.contact_refs[key].asset_id) || ''
    initialVoice.mode = form.voiceMode
    initialVoice.assetId = form.voiceAssetId
    initialVoice.contact = contactName
    voiceLoaded.value = true
  } catch (err) {
    voiceError.value = err.message || String(err)
  } finally {
    voiceLoading.value = false
  }
}

async function saveVoiceBinding(contactName, choice) {
  const body = { action: 'bind', contact: contactName }
  const renamed = contactName !== initialVoice.contact
  if (renamed || choice.mode !== initialVoice.mode) body.mode = choice.mode
  if (renamed || choice.assetId !== initialVoice.assetId) body.asset_id = choice.assetId
  if (!voiceLoaded.value || Object.keys(body).length === 2) return
  const response = await fetch('/api/voice-assets', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Wxbot-Voice-Action': '1'
    },
    body: JSON.stringify(body)
  })
  const text = await response.text()
  const result = text ? JSON.parse(text) : {}
  if (!response.ok) throw new Error(result.error || '保存音色绑定失败')
  initialVoice.mode = choice.mode
  initialVoice.assetId = choice.assetId
  initialVoice.contact = contactName
  return result
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
    if (voiceLoading.value || ttsLoading.value || webPresetLoading.value) throw new Error('配置正在读取，请稍后保存。')
    const voiceChoice = { mode: form.voiceMode, assetId: form.voiceAssetId }
    const requestedPreset = form.webuiPreset
    const requestedTtsEnabled = form.indexTtsEnabled
    const body = {
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
    }
    if (form.indexTtsEnabled !== initialTtsEnabled) {
      if (!ttsLoaded.value || !ttsAvailable.value || !ttsPolicy?.role_skill) {
        throw new Error('请先读取技能目录，并在 AI 设置中选择角色。')
      }
      const allowed = new Set(ttsPolicy.allowed_skills)
      if (form.indexTtsEnabled) allowed.add('index-tts')
      else allowed.delete('index-tts')
      body.policy = { ...ttsPolicy, allowed_skills: [...allowed] }
    }
    data.value = await contactRequest({ version: data.value.version, ...body })
    const savedConversation = (data.value.rows || []).flatMap(row => row.conversations || []).find(c => c.id === body.id)
    if (!savedConversation?.name) throw new Error('会话资料已保存，但返回缺少会话标识，语音配置尚未保存；请刷新后重试。')
    const savedName = savedConversation.name
    form.name = savedName
    if (body.policy) {
      ttsPolicy = body.policy
      initialTtsEnabled = requestedTtsEnabled
    }
    try {
      // Only changed fields are written; a mode edit must not clear a legacy ref_wav.
      await saveVoiceBinding(savedName, voiceChoice)
    } catch (err) {
      throw new Error('会话资料与技能授权已保存，语音设置尚未保存：' + (err.message || String(err)))
    }
    try {
      await saveWebPreset(savedName, requestedPreset)
    } catch (err) {
      throw new Error('会话资料与语音设置已保存，网页预设尚未保存：' + (err.message || String(err)))
    }
    closeDialog()
    error.value = ''
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
          <label>微信窗口名称<input v-model="form.name" name="name" required :disabled="dialogBusy"></label>
          <p>用于在微信主窗口定位聊天：微信主窗口里能搜到的会话名，bot 靠它把消息投递到这个窗口。改错会导致发不出去。</p>
          <div class="user-check-row">
            <label class="user-check"><input v-model="form.enabled" name="enabled" type="checkbox" :disabled="dialogBusy">启用此目的地</label>
            <label class="user-check"><input v-model="form.listening" name="listening" type="checkbox" :disabled="dialogBusy">监听此会话</label>
          </div>
          <fieldset :disabled="dialogBusy">
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
            <label>uid<input v-model="form.uid" name="uid" :disabled="dialogBusy"></label>
            <label>profile<input v-model="form.profile" name="profile" :disabled="dialogBusy"></label>
            <label>label<input v-model="form.label" name="label" :disabled="dialogBusy"></label>
            <label>session_key<input v-model="form.session_key" name="session_key" :disabled="dialogBusy"></label>
          </details>
          <fieldset id="contact-index-tts" :disabled="dialogBusy">
            <legend>IndexTTS 文字转语音</legend>
            <p v-if="ttsLoading" class="user-hint" role="status">读取技能授权…</p>
            <p v-else-if="ttsError" class="user-error" role="alert">{{ ttsError }} <button type="button" @click="loadTtsCatalogue">重试读取技能</button></p>
            <label class="user-check">
              <input v-model="form.indexTtsEnabled" name="indexTtsEnabled" type="checkbox"
                :disabled="!ttsLoaded || !ttsAvailable || !ttsPolicy?.role_skill" aria-describedby="contact-index-tts-help">
              允许此会话使用 IndexTTS
            </label>
            <p id="contact-index-tts-help" class="user-hint">在下方绑定网页音色后，聊天中提供文字即可使用；明确指定其他预设时优先使用指定值。长文本自动分段，其余参数用网页默认值。</p>
            <label for="contact-webui-preset">网页音色预设</label>
            <div class="tts-preset-controls">
              <select id="contact-webui-preset" v-model="form.webuiPreset" name="webuiPreset"
                :disabled="!webPresetLoaded || webPresetLoading" aria-describedby="contact-webui-preset-status">
                <option value="">不绑定（在聊天中指定）</option>
                <option v-if="form.webuiPreset && !webPresets.includes(form.webuiPreset)" :value="form.webuiPreset">{{ form.webuiPreset }}（网页暂无法确认）</option>
                <option v-for="preset in webPresets" :key="preset" :value="preset">{{ preset }}</option>
              </select>
              <button type="button" :disabled="webPresetLoading" @click="loadWebPresets(payload.name)">刷新网页预设</button>
            </div>
            <p v-if="webPresetLoading" id="contact-webui-preset-status" class="user-hint" role="status">读取 IndexTTS 网页预设…</p>
            <p v-else-if="webPresetError" id="contact-webui-preset-status" class="user-error" role="alert">{{ webPresetError }}</p>
            <p v-else id="contact-webui-preset-status" class="user-hint">{{ webPresets.length ? '此列表来自 IndexTTS 网页保存的预设，保存会话后作为默认音色。' : '网页还没有可选预设，请在 IndexTTS 中保存音色后刷新。' }}</p>
            <p v-if="ttsLoaded && !ttsAvailable" class="user-hint contact-tts-warning">此安装未提供 index-tts 技能，请检查插件后重试。</p>
            <p v-else-if="!ttsPolicy?.role_skill" class="user-hint contact-tts-warning">请先在联系人的「AI 设置」中选择角色，再授权此功能。</p>
            <p v-if="!payload.policy && ttsPolicy" class="user-hint">修改授权会为此窗口保存独立策略，保留当前角色、其他技能和自动问候设置。</p>
            <p v-if="form.indexTtsEnabled && form.voiceMode === 'off'" class="user-hint contact-tts-warning">还需将下方语音发送模式设为替换或并存，才能发送 IndexTTS 语音。</p>
          </fieldset>
          <fieldset class="voice-bind-fieldset" :disabled="dialogBusy || voiceLoading">
            <legend>语音回复</legend>
            <p v-if="voiceLoading" class="user-hint" role="status">读取语音设置…</p>
            <p v-else-if="voiceError" class="user-error" role="alert">{{ voiceError }} <button type="button" @click="loadVoiceBinding(payload.name)">重试读取语音设置</button></p>
            <p class="user-hint">自动语音回复需绑定下方音色；IndexTTS 使用网页音色预设，无需另绑音色资产。两者都需要开启语音总开关及本会话语音模式。</p>
            <label>
              语音发送模式
              <select v-model="form.voiceMode" name="voiceMode" :disabled="!voiceLoaded">
                <option value="off">关闭（文字）</option>
                <option value="replace">替换为语音</option>
                <option value="coexist">文字与语音并存</option>
              </select>
            </label>
            <label>
              自动回复音色
              <select v-model="form.voiceAssetId" name="voiceAssetId" :disabled="!voiceLoaded">
                <option value="">不绑定</option>
                <option v-for="asset in voiceAssets" :key="asset.id" :value="asset.id">{{ asset.name }}</option>
              </select>
            </label>
            <p v-if="voiceLoaded && !voiceEnabled" class="user-hint contact-tts-warning">语音总开关当前关闭；可先保存配置，使用前在「配置管理」启用 voice.enabled，并手动重启 wxbot。</p>
          </fieldset>
          <button type="submit" :disabled="dialogBusy || voiceLoading || ttsLoading || webPresetLoading">{{ dialogBusy ? '保存中…' : '保存会话' }}</button>
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
              <span>{{ skill.name === 'index-tts' ? 'IndexTTS 文字转语音' : skill.name }}<small>{{ skill.description || '' }}</small></span>
            </label>
            <label v-for="name in unavailableSkills" :key="'unavailable-' + name" class="user-skill">
              <input v-model="form.allowed" type="checkbox" name="skill" :value="name" :disabled="dialogBusy">
              <span>{{ name }}（未安装）<small>此功能当前不可用。取消勾选后可移除旧配置并保存。</small></span>
            </label>
          </fieldset>
          <label class="user-check"><input v-model="form.heartbeat" name="heartbeat" type="checkbox">自动问候</label>
          <p>{{ payload.conversation ? '主动问候与订阅继续投递到此窗口。' : '个人主动问候必须配置明确的私聊目的地。' }}保存角色和 Skill 后后续请求生效。</p>
          <p v-if="!loading && !loaded" class="user-hint">技能目录没读出来，此时保存会把角色清空；先处理好上面的错误再回来。</p>
          <button type="submit" :disabled="dialogBusy || !loaded">{{ dialogBusy ? '保存中…' : '保存策略' }}</button>
        </form>

        <div v-else-if="mode === 'relations'" class="user-form">
          <form id="contact-link-form" class="user-form user-section" @submit.prevent="submitLink">
            <h3>关联已有群成员</h3>
            <label>
              已有群成员
              <select v-model="form.binding" name="binding" required>
                <option value="">选择已核对的成员</option>
                <option v-for="member in candidates()" :key="'cand-' + member.binding_id" :value="member.binding_id">
                  {{ member.person }}，{{ member.contact }}－{{ member.nickname }}{{ member.enabled ? '' : '，已停用' }}
                </option>
              </select>
            </label>
            <p>所选成员及同一固定用户的全部关系归并到「{{ payload.name }}」。保留各群昵称与停用开关；具体资料在各自的知识库里维护。</p>
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
            <p>此操作明确确认身份，并将成员关系关联到当前联系人。</p>
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
