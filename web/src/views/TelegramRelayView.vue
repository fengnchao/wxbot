<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost, clone, fullTime } from '../api'

defineProps({ tab: { type: String, default: '' } })
const ctx = inject('logWebCtx')

const LABELS = {
  enabled: '启用监听',
  include_text: '保留正文',
  include_images: '图片继续投递到微信',
  include_source: '保留来源',
  include_time: '保留原发布时间',
  window_title: 'Telegram 窗口标题',
  bot_username: '现有机器人用户名',
  bot_id: '现有机器人数字 ID',
  poll_interval: '轮询间隔（秒）',
  album_quiet_seconds: '图集静默等待（秒）',
  max_album_wait: '图集最长等待（秒）'
}
const FLAGS = ['enabled', 'include_text', 'include_images', 'include_source', 'include_time']
const FIELDS = ['window_title', 'bot_username', 'bot_id', 'poll_interval', 'album_quiet_seconds', 'max_album_wait']
const NUMBERS = new Set(['bot_id', 'poll_interval', 'album_quiet_seconds', 'max_album_wait'])
const COLUMNS = [
  ['key', '稳定频道键'],
  ['name', '频道名称'],
  ['username', '频道用户名'],
  ['chat_id', '频道数字 ID']
]

const draft = ref(null)
const version = ref('')
const note = ref('')
const runtime = ref(null)
const adminText = ref('')
const desktopText = ref(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const ack = ref({})

const ready = computed(() => !!draft.value)
const tasks = computed(() => (Array.isArray(runtime.value?.tasks) ? runtime.value.tasks : []))
const countsText = computed(() => Object.entries(runtime.value?.counts || {})
  .map(([key, value]) => key + '：' + value).join(' · '))
const runtimeChannels = computed(() => {
  const value = runtime.value?.channels
  if (Array.isArray(value)) return value
  return Object.entries(value || {}).map(([key, item]) => (
    typeof item === 'object' && item ? { key, ...item } : { key, state: item }
  ))
})
const channelNames = computed(() => new Map((draft.value?.channels || []).map(channel => [channel.key, channel.name])))
const desktopValue = computed({
  get: () => desktopText.value === null
    ? JSON.stringify(draft.value?.desktop ?? {}, null, 2)
    : desktopText.value,
  set: value => { desktopText.value = value }
})

async function load() {
  try {
    const payload = await apiGet('/api/telegram-relay')
    note.value = payload.note || ''
    version.value = payload.version
    runtime.value = payload.runtime
    draft.value = clone(payload.settings)
    adminText.value = (payload.settings.admin_contacts || []).join('\n')
    desktopText.value = null
    error.value = ''
    ack.value = {}
    ctx?.markRefreshed()
  } catch (failure) {
    error.value = failure.message
  }
}

function reviewable(task) {
  const id = String(task.id || '')
  return ['blocked', 'uncertain'].includes(task.state) && (id === 'desktop' || /^[a-f0-9]{32}$/.test(id))
}

function channelName(task) {
  return channelNames.value.get(task.channel) || task.channel || '未知频道'
}

function buildSettings() {
  const value = clone(draft.value)
  value.admin_contacts = adminText.value.split('\n').map(line => line.trim()).filter(Boolean)
  for (const key of ['bot_id', 'poll_interval', 'album_quiet_seconds', 'max_album_wait']) {
    value[key] = Number(value[key]) || 0
  }
  value.channels = (value.channels || []).map(channel => ({ ...channel, chat_id: Number(channel.chat_id) || 0 }))
  if (desktopText.value !== null) value.desktop = JSON.parse(desktopText.value)
  return value
}

async function save() {
  if (busy.value) return
  let settings
  try {
    settings = buildSettings()
  } catch {
    error.value = '控件校准需为有效的 JSON 对象；草稿已保留'
    return
  }
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = await apiPost('/api/telegram-relay', { settings, version: version.value }, 'X-Wxbot-Relay-Action')
    note.value = payload.note || note.value
    version.value = payload.version
    runtime.value = payload.runtime
    draft.value = clone(payload.settings)
    adminText.value = (payload.settings.admin_contacts || []).join('\n')
    desktopText.value = null
    message.value = '已保存，现有服务下次读取生效。'
    ctx?.markRefreshed()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

async function discard() {
  desktopText.value = null
  error.value = ''
  message.value = ''
  await load()
}

async function resolve(task, action) {
  if (busy.value) return
  if (!ack.value[task.id]) {
    error.value = '请先核对发送结果、清理 Telegram 残留界面，并勾选此任务的确认框。'
    return
  }
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await apiPost('/api/telegram-relay/resolve', { id: task.id, action, acknowledge: true }, 'X-Wxbot-Relay-Action')
    message.value = '核对结果已提交；正在刷新运行状态。'
    await load()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

function addChannel() {
  draft.value.channels.push({ key: '', name: '', username: '', chat_id: 0, enabled: false })
}

function removeChannel(index) {
  draft.value.channels.splice(index, 1)
}

onMounted(load)
watch(() => ctx?.refreshKey.value, load)
</script>

<template>
  <aside id="list">
    <div class="head" style="margin:10px">
      <h2>Telegram 转发</h2>
      <p class="muted">频道 → 现有机器人 → 新闻分组 → 微信</p>
    </div>
  </aside>

  <section id="pane">
    <div class="head">
      <h2>Telegram 频道转发</h2>
      <p>{{ note }}</p>
      <p>目标用户名和数字 ID 必须与当前接收机器人的身份一致。管理员名单之外的会话不能通过 Skill 暂停或恢复。</p>
    </div>

    <div v-if="!ready" class="empty">{{ error || '载入转发设置…' }}</div>

    <template v-else>
      <div class="card">
        <h3>监听与内容</h3>
        <div>
          <label v-for="key in FLAGS" :key="key" style="margin-right:14px">
            <input v-model="draft[key]" type="checkbox" :disabled="busy"> {{ LABELS[key] }}
          </label>
        </div>
        <label v-for="key in FIELDS" :key="key" style="display:block;margin:10px 0">
          {{ LABELS[key] }}
          <input
            v-model="draft[key]"
            :type="NUMBERS.has(key) ? 'number' : 'text'"
            :disabled="busy"
            style="display:block;width:100%;box-sizing:border-box"
          >
        </label>
        <label>
          允许使用管理 Skill 的微信会话（每行一个）
          <textarea v-model="adminText" rows="3" :disabled="busy" style="display:block;width:100%;box-sizing:border-box"></textarea>
        </label>
        <p class="muted">首次历史：只建立基线；图片失败：保留待处理。</p>
      </div>

      <div class="card">
        <h3>频道列表</h3>
        <p class="muted">稳定频道键用于保存游标，修改显示名称请保留此键。启用频道需提供用户名或数字 ID。</p>
        <div class="monitor-table-wrap">
          <table class="monitor-table">
            <thead>
              <tr>
                <th>启用</th>
                <th v-for="[key, label] in COLUMNS" :key="key">{{ label }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(channel, index) in draft.channels" :key="index">
                <td><input v-model="channel.enabled" type="checkbox" :aria-label="'频道启用'" :disabled="busy"></td>
                <td v-for="[key] in COLUMNS" :key="key">
                  <input
                    v-model="channel[key]"
                    :type="key === 'chat_id' ? 'number' : 'text'"
                    :aria-label="COLUMNS.find(item => item[0] === key)[1]"
                    :disabled="busy"
                    style="width:100%;box-sizing:border-box"
                  >
                </td>
                <td><button :disabled="busy" @click="removeChannel(index)">删除</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <button :disabled="busy" @click="addChannel">新增频道</button>
      </div>

      <details class="card" data-detail="relay-selectors">
        <summary>Telegram 控件校准</summary>
        <p class="muted">由管理员填写控件名称；无法确认窗口或来源时，监听会停留在待校准状态。</p>
        <textarea v-model="desktopValue" rows="8" spellcheck="false" :disabled="busy"
                  style="display:block;width:100%;box-sizing:border-box"></textarea>
      </details>

      <div class="card">
        <p role="status" :class="error ? 'warn' : 'muted'">{{ error || message }}</p>
        <button :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存设置' }}</button>
        <button :disabled="busy" @click="discard">放弃草稿并刷新</button>
      </div>

      <div class="card">
        <h3>运行与队列状态</h3>
        <p v-if="!runtime || runtime.state === 'unavailable'" class="muted">暂无运行快照；配置开关不代表服务已运行。</p>
        <template v-else>
          <p>当前阶段：{{ runtime.phase || '等待扫描' }} · 最近更新：{{ runtime.at ? fullTime(runtime.at) : '未知' }}</p>
          <p>{{ countsText }}</p>
          <p v-if="runtime.error" class="warn">{{ runtime.error }}</p>
          <div v-for="channel in runtimeChannels" :key="channel.key" class="card">
            <strong>{{ channel.name || channel.key || '频道' }}</strong>
            <div>{{ channel.phase || channel.state || channel.status || '等待扫描' }}</div>
            <div class="muted">最近扫描：{{ channel.last_scan || channel.scanned_at || '暂无' }} {{ channel.error || '' }}</div>
          </div>
        </template>
      </div>

      <div v-if="runtime?.ui_hold || tasks.length" class="card">
        <h3>转发任务与人工核对</h3>
        <p v-if="runtime?.ui_hold" class="warn" role="status">桌面已暂停，等待人工核对。重启或暂停／恢复不会解除此状态。</p>
        <p>先核对 Telegram 机器人实际收件及对应来源，再清理 Telegram 残留搜索、菜单和转发弹层。确认未发送后才可重试，避免重复转发。确认已转发仅记录 Telegram 阶段，不代表微信已送达。</p>
        <div v-for="task in tasks" :key="task.id" class="card">
          <strong>{{ task.id === 'desktop' ? '桌面界面核对' : channelName(task) }}</strong>
          <p>
            频道键：{{ task.channel || '未知' }} · 消息 ID：{{ task.id === 'desktop' ? '无消息任务' : (task.source_id || '尚未取得，请核对来源') }}<br>
            任务 ID：{{ task.id }} · 状态：{{ task.state || '未知' }} · {{ task.submitted ? '曾进入提交阶段' : '尚无提交标记' }}<br>
            更新时间：{{ task.updated ? fullTime(task.updated) : '未知' }}
          </p>
          <p v-if="task.error" class="warn">{{ task.error }}</p>
          <template v-if="reviewable(task)">
            <label>
              <input v-model="ack[task.id]" type="checkbox" :disabled="busy">
              我已核实此任务的发送结果，并清理 Telegram 残留界面
            </label>
            <div>
              <button v-if="task.id !== 'desktop'" :disabled="busy" @click="resolve(task, 'forwarded')">确认已转发</button>
              <button :disabled="busy" @click="resolve(task, 'retry')">{{ task.id === 'desktop' ? '界面已清理，继续' : '确认未发，重试' }}</button>
              <button :disabled="busy" @click="resolve(task, 'cancelled')">{{ task.id === 'desktop' ? '界面已清理，放弃本次操作' : '放弃' }}</button>
            </div>
          </template>
        </div>
      </div>
    </template>
  </section>
</template>
