<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiGet, fullTime } from '../api'

const ctx = inject('logWebCtx', null)
const data = ref(null)
const bindings = ref(null)
const loading = ref(true)
const error = ref('')
const message = ref('')
const busy = ref('')
const name = ref('')
const file = ref(null)
const fileInput = ref(null)
const playingId = ref('')
let audio = null
let request = 0

const assets = computed(() => Array.isArray(data.value?.assets) ? data.value.assets : [])
const limits = computed(() => data.value?.limits || {})
const query = computed(() => String(ctx?.search?.['voice-assets'] || '').trim().toLowerCase())
const visible = computed(() => {
  const q = query.value
  if (!q) return assets.value
  return assets.value.filter(item =>
    [item.name, item.id, item.filename].some(v => String(v || '').toLowerCase().includes(q)))
})

watch(() => ctx?.refreshKey?.value, () => load())
onMounted(load)
onUnmounted(() => stopPreview())

async function load() {
  const mine = ++request
  loading.value = true
  error.value = ''
  try {
    const [list, bind] = await Promise.all([
      apiGet('/api/voice-assets'),
      apiGet('/api/voice-bindings')
    ])
    if (mine !== request) return
    data.value = list
    bindings.value = bind
  } catch (err) {
    if (mine !== request) return
    error.value = err.message || String(err)
  } finally {
    if (mine === request) loading.value = false
  }
}

function boundContacts(assetId) {
  const refs = bindings.value?.contact_refs || {}
  return Object.entries(refs)
    .filter(([, value]) => String(value?.asset_id || '') === assetId)
    .map(([contact]) => contact)
}

function onFile(event) {
  file.value = event.target.files?.[0] || null
}

function readFileAsBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(new Error('读取文件失败'))
    reader.readAsDataURL(blob)
  })
}

async function voicePost(body) {
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
  let payload = null
  try { payload = text ? JSON.parse(text) : null } catch { payload = null }
  if (!response.ok) throw new Error((payload && payload.error) || ('请求失败 HTTP ' + response.status))
  return payload
}

async function registerAsset() {
  if (!name.value.trim()) {
    error.value = '请填写音色名称'
    return
  }
  if (!file.value) {
    error.value = '请选择参考 WAV 文件'
    return
  }
  if (!String(file.value.name || '').toLowerCase().endsWith('.wav')) {
    error.value = '仅支持 WAV 参考音'
    return
  }
  busy.value = 'register'
  error.value = ''
  message.value = ''
  try {
    const dataBase64 = await readFileAsBase64(file.value)
    await voicePost({ action: 'register', name: name.value.trim(), data_base64: dataBase64 })
    name.value = ''
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
    message.value = '已注册音色（参考音预览与绑定可用）'
    await load()
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    busy.value = ''
  }
}

async function renameAsset(asset) {
  const next = window.prompt('新的音色名称', asset.name)
  if (next == null) return
  const label = String(next).trim()
  if (!label) {
    error.value = '名称不能为空'
    return
  }
  busy.value = 'rename:' + asset.id
  error.value = ''
  message.value = ''
  try {
    await voicePost({ action: 'rename', id: asset.id, name: label })
    message.value = '已改名'
    await load()
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    busy.value = ''
  }
}

async function deleteAsset(asset) {
  const bound = boundContacts(asset.id)
  const tip = bound.length
    ? ('删除「' + asset.name + '」将同时清除 ' + bound.length + ' 个会话绑定，确认？')
    : ('确认删除音色「' + asset.name + '」？本地参考音文件会一并删除。')
  if (!window.confirm(tip)) return
  busy.value = 'delete:' + asset.id
  error.value = ''
  message.value = ''
  try {
    const result = await voicePost({ action: 'delete', id: asset.id })
    message.value = '已删除' + ((result.cleared_contacts || []).length
      ? ('，并清除绑定：' + result.cleared_contacts.join('、'))
      : '')
    if (playingId.value === asset.id) stopPreview()
    await load()
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    busy.value = ''
  }
}

function stopPreview() {
  if (audio) {
    try { audio.pause() } catch {}
    audio = null
  }
  playingId.value = ''
}

function pLabel(asset) {
  return playingId.value === asset.id ? '停止' : '试听'
}

async function previewAsset(asset) {
  if (playingId.value === asset.id) {
    stopPreview()
    return
  }
  stopPreview()
  busy.value = 'preview:' + asset.id
  error.value = ''
  try {
    const response = await fetch('/api/voice-assets/preview?id=' + encodeURIComponent(asset.id), {
      headers: { Accept: 'audio/wav,application/json' }
    })
    if (!response.ok) {
      let detail = '试听失败'
      try {
        const payload = await response.json()
        detail = payload.error || detail
      } catch {}
      throw new Error(detail)
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    audio = new Audio(url)
    playingId.value = asset.id
    audio.onended = () => {
      URL.revokeObjectURL(url)
      playingId.value = ''
      audio = null
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      playingId.value = ''
      audio = null
      error.value = '浏览器无法播放该参考音'
    }
    await audio.play()
  } catch (err) {
    error.value = err.message || String(err)
    stopPreview()
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <section id="pane" class="voice-assets" aria-labelledby="voice-assets-title">
    <header class="voice-assets-head">
      <div>
        <h2 id="voice-assets-title">音色资产</h2>
        <p>注册参考音（zero-shot），供会话绑定后合成；试听播放已注册参考 WAV，不触发 IndexTTS。</p>
      </div>
      <p class="voice-assets-meta" v-if="limits.max_bytes">
        上限 {{ Math.round(limits.max_bytes / (1024 * 1024)) }} MiB · 格式 WAV
      </p>
    </header>

    <p v-if="error" class="voice-error" role="alert">{{ error }}</p>
    <p v-if="message" class="voice-ok" role="status">{{ message }}</p>
    <p v-if="loading" class="voice-muted">读取音色清单…</p>

    <form class="voice-register" @submit.prevent="registerAsset">
      <label>
        音色名称
        <input v-model="name" name="name" maxlength="80" required placeholder="例如：客服女声 A" autocomplete="off">
      </label>
      <label>
        参考 WAV
        <input ref="fileInput" type="file" accept="audio/wav,.wav" @change="onFile">
      </label>
      <button type="submit" :disabled="busy === 'register'">添加音色</button>
    </form>

    <div class="voice-table-wrap">
      <table class="voice-table">
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">创建时间</th>
            <th scope="col">时长</th>
            <th scope="col">绑定会话</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!visible.length">
            <td colspan="5" class="voice-muted">还没有音色。上传一段本人授权的参考 WAV 后即可绑定到会话。</td>
          </tr>
          <tr v-for="asset in visible" :key="asset.id">
            <td>
              <strong>{{ asset.name }}</strong>
              <div class="voice-muted">{{ asset.id }}</div>
            </td>
            <td>{{ fullTime(asset.created_at) }}</td>
            <td>{{ asset.duration_seconds ? asset.duration_seconds.toFixed(1) + 's' : '-' }}</td>
            <td>
              <span v-if="boundContacts(asset.id).length">{{ boundContacts(asset.id).join('、') }}</span>
              <span v-else class="voice-muted">未绑定</span>
            </td>
            <td class="voice-actions">
              <button type="button" class="voice-preview" @click="previewAsset(asset)" :disabled="busy.startsWith('preview')">
                {{ pLabel(asset) }}
              </button>
              <button type="button" @click="renameAsset(asset)" :disabled="!!busy">改名</button>
              <button type="button" class="danger" @click="deleteAsset(asset)" :disabled="!!busy">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
