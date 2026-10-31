<script setup>
import { computed, inject, onMounted, watch } from 'vue'
import { apiGet } from '../api'
import ConfigField from '../components/ConfigField.vue'
import {
  busy, busyTotal, data, dirtyTotal, drafts, error, messages, section, search
} from '../configDraft'
import { go } from '../router'

const ctx = inject('logWebCtx', null)

const CATEGORIES = [
  ['basic', '基础连接'], ['wechat', '微信收发'], ['model', '模型后端'],
  ['contacts', '联系人与策略'], ['logging', '日志'], ['advanced', '高级配置']
]
const HIDDEN_SECTIONS = new Set(['log', 'log.flow_trace', 'wxbot.typing', 'wxbot.failure_policy'])
const EDITORS = ['boolean', 'integer', 'number', 'string', 'json', 'secret']
const LIST_WIDGETS = ['string-list', 'contacts', 'directory-contacts', 'alias-list']
const MODE_LABELS = { full: '全量粘贴', chunked: '分字粘贴', streaming: '流式粘贴' }

let request = 0

const allRows = computed(() => (data.value?.sections || []).flatMap(item => item.rows))
// 兼容配置判定依赖当前选择的后端，用 computed 缓存一次计算结果。
function selectedValue(key) {
  const row = allRows.value.find(row => row.key === key)
  const sourceId = key.split('.')[0]
  const draft = row && draftOf(sourceId, row)
  return draft?.op === 'set' ? draft.raw : draft?.op === 'default' ? (key === 'butler.agent.provider' ? 'hermes' : '') : row?.value
}
// 草稿优先；没有草稿或恢复默认时用服务端按文件算出的接入方式。
function draftRaw(key) {
  const row = allRows.value.find(item => item.key === key)
  const draft = row && draftOf(key.split('.')[0], row)
  return draft?.op === 'set' ? draft.raw : undefined
}
const backendName = computed(() =>
  draftRaw('butler.model.provider') ?? data.value?.model_access?.current ?? 'hermes')
const modelBackend = computed(() => selectedValue('wxbot.model.backend'))
const genericModel = computed(() => allRows.value.some(row => row.key.startsWith('butler.model.') && row.origin === 'file') || Boolean(drafts.value.butler && Object.values(drafts.value.butler.changes).some(change => change.path[0] === 'model')))

// 哪些字段要填由接入方式决定；规则随接口下发，草稿改动后立刻生效。
function applicable(item, row) {
  if (item.id !== 'butler.model') return true
  const last = row.path?.at(-1)
  if (last === 'provider') return true
  const fields = data.value?.model_access?.fields?.[backendName.value]
  return (fields || ['url', 'model', 'api_key', 'timeout', 'max_history', 'system_prompt']).includes(last)
}
const searching = computed(() => Boolean(search.value.trim()))

const paneTitle = computed(() => {
  if (searching.value) return '配置搜索结果'
  const found = CATEGORIES.find(category => category[0] === section.value)
  return found ? found[1] : '全部配置'
})

const navCategories = computed(() => {
  const rows = (data.value?.sections || [])
    .filter(item => !HIDDEN_SECTIONS.has(item.id))
    .flatMap(item => item.rows.map(row => ({ item, row })))
  return CATEGORIES.concat([['all', '全部参数']]).map(([id, title]) => ({
    id,
    title,
    count: rows.filter(({ item, row }) => (id === 'all' || categoryOf(item, row) === id) && (id === 'all' || id === 'advanced' || applicable(item, row)) && matches(item, row)).length
  }))
})

const visibleSections = computed(() => {
  const list = (data.value?.sections || []).filter(item => !HIDDEN_SECTIONS.has(item.id))
  return list
    .map(item => {
      const rows = item.rows.filter(row => (section.value === 'advanced' || section.value === 'all' || applicable(item, row)) && matches(item, row) &&
        (searching.value || section.value === 'all' || section.value === item.id || categoryOf(item, row) === section.value))
      return {
        id: item.id,
        title: item.title,
        section: item,
        rows,
        advanced: rows.every(row => categoryOf(item, row) === 'advanced') ||
          ['policies', 'log_policies', 'groups', 'log_groups'].includes(item.source_id),
        compatibility: rows.some(row => compatibilityOf(item, row))
      }
    })
    .filter(entry => entry.rows.length)
})

const visibleSourceIds = computed(() => new Set(visibleSections.value.map(entry => entry.section.source_id)))

// 只列出与本页相关内容有关的来源；有草稿、有提示或读取错误的来源始终保留。
const sourceActions = computed(() => (data.value?.sources || []).filter(source =>
  visibleSourceIds.value.has(source.id) || drafts.value[source.id] ||
  messages.value[source.id] || busy.value[source.id] || source.status === 'error'
))

const dirtyCount = computed(() => dirtyTotal())

onMounted(() => load())
watch(() => ctx?.refreshKey?.value, () => load())

function matches(item, row) {
  const query = search.value.trim().toLowerCase()
  if (!query) return true
  const text = [
    item.title, item.source, row.key, row.label, row.description, row.effect,
    row.sensitive ? '' : JSON.stringify(row.value)
  ].join(' ').toLowerCase()
  return text.includes(query)
}

function compatibilityOf(item, row) {
  const id = item.id || ''
  // 接入方式是模型页的入口，任何情况下都要能改，否则选了 Codex 就切不回来。
  if (row.path?.join('.') === 'model.provider') return false
  return (id === 'butler.hermes' && (backendName.value !== 'hermes' || genericModel.value || Boolean(drafts.value.butler?.changes[JSON.stringify(['agent','provider'])]))) ||
    (id === 'butler.model' && (['codex', 'echo'].includes(backendName.value) || backendName.value === 'hermes' && !genericModel.value && !drafts.value.butler?.changes[JSON.stringify(['agent','provider'])] || !applicable(item, row))) ||
    (id === 'butler.codex' && backendName.value !== 'codex') ||
    id === 'butler.dispatch' ||
    (id === 'wxbot.model' && row.path?.at(-1) !== 'backend' && modelBackend.value === 'butler')
}

function categoryOf(item, row) {
  const id = item.id || ''
  const key = row.key || ''
  if (!row.editable || compatibilityOf(item, row)) return 'advanced'
  if (['contacts', 'directory', 'policies', 'log_policies', 'groups', 'log_groups'].includes(item.source_id) ||
    key.startsWith('butler.contacts')) return 'contacts'
  if (id === 'log_config' || id === 'butler.log') return 'logging'
  if (['butler.codex', 'butler.hermes', 'butler.model', 'wxbot.model'].includes(id)) return 'model'
  // 实际调用协议由接入方式推导，放进高级配置，避免同一件事占两个下拉。
  if (key === 'butler.agent.provider') return 'advanced'
  if (['wxbot.butler', 'butler.server', 'butler.agent'].includes(id)) return 'basic'
  if (['butler.heartbeat', 'butler.groups'].includes(id)) return 'contacts'
  if (item.source_id === 'wxbot') return 'wechat'
  return 'advanced'
}

function sourceById(id) {
  return (data.value?.sources || []).find(source => source.id === id)
}

function isEditable(source, row) {
  return Boolean(source) && source.status !== 'error' && typeof source.version === 'string' && source.version &&
    row.editable === true && Array.isArray(row.path) && row.path.length && EDITORS.includes(row.editor)
}

function rawOf(row) {
  if (row.editor === 'secret') return ''
  return typeof row.value === 'string' ? row.value : (JSON.stringify(row.value, null, 2) ?? '')
}

function draftOf(sourceId, row) {
  return drafts.value[sourceId]?.changes[JSON.stringify(row.path)]
}

function kindOf(row, raw) {
  if (row.editor === 'secret') return 'secret'
  if (row.choices?.length) return 'select'
  if (row.editor === 'boolean') return 'select'
  if (row.editor === 'integer' || row.editor === 'number') return 'number'
  if (LIST_WIDGETS.includes(row.widget)) return 'structured'
  if (row.editor === 'string' && !raw.includes('\n') && raw.length < 160) return 'text'
  return 'textarea'
}

function choicesOf(row, raw) {
  if (row.choices?.length) {
    const list = [...new Set([...row.choices, ...(raw && !row.choices.includes(raw) ? [raw] : [])])]
    const labels = row.choice_labels || []
    const typed = row.path?.join('.') === 'wechat.typing.mode'
    return list.map(value => ({
      value,
      label: typed ? (MODE_LABELS[value] || value) : (labels[row.choices.indexOf(value)] || value)
    }))
  }
  if (row.editor === 'boolean') {
    return [{ value: 'true', label: '开启（true）' }, { value: 'false', label: '关闭（false）' }]
  }
  return []
}

// 一次组装出 ConfigField 需要的全部派生字段，模板只负责摆放。
function fieldOf(item, row) {
  const source = sourceById(item.source_id)
  const draft = draftOf(item.source_id, row)
  // 接入方式没显式存过时显示服务端推导出的当前值，避免下拉停在空选项。
  const isAccess = row.path?.join('.') === 'model.provider'
  const raw = draft?.op === 'set' ? draft.raw
    : isAccess ? (row.value || data.value?.model_access?.current || '') : rawOf(row)
  const editable = isEditable(source, row)
  const disabled = Boolean(busy.value[item.source_id])
  return {
    row,
    editable,
    disabled,
    raw,
    label: row.label || String(row.key || '').split('.').at(-1),
    description: row.description || '',
    note: row.path?.join('.') === 'model.provider'
      ? (data.value?.model_access?.notes?.[backendName.value] || row.note || '') : '',
    placeholder: row.placeholder || '',
    effect: row.effect || '',
    sensitive: Boolean(row.sensitive),
    defaultAvailable: Boolean(row.default_available),
    kind: editable ? kindOf(row, raw) : 'text',
    step: row.editor === 'integer' ? 1 : 'any',
    choices: editable ? choicesOf(row, raw) : [],
    mode: row.editor === 'secret' ? (draft?.op || 'keep') : 'keep',
    draftOp: draft?.op || ''
  }
}

function updateDraft(item, field, raw, op = 'set') {
  const row = field.row
  const sourceId = item.source_id
  const source = sourceById(sourceId)
  if (busy.value[sourceId] || !isEditable(source, row)) return
  if (op === 'default' && !row.default_available) return
  if (op === 'clear' && row.editor !== 'secret') return
  if (!['set', 'clear', 'default', 'keep'].includes(op)) return
  const key = JSON.stringify(row.path)
  const unchanged = op === 'keep' || (op === 'set' && row.editor !== 'secret' && String(raw) === rawOf(row))
  const draft = drafts.value[sourceId]
  if (unchanged) {
    if (draft) {
      delete draft.changes[key]
      if (!Object.keys(draft.changes).length) delete drafts.value[sourceId]
    }
  } else {
    if (!drafts.value[sourceId]) drafts.value[sourceId] = { version: source.version, changes: {} }
    drafts.value[sourceId].changes[key] = { path: row.path.slice(), op, raw: String(raw ?? ''), row }
  }
  delete messages.value[sourceId]
}

function statusOf(source) {
  if (!source) return { text: '', error: false }
  if (busy.value[source.id]) return { text: '正在保存…' }
  const message = messages.value[source.id]
  if (message) return message
  const count = Object.keys(drafts.value[source.id]?.changes || {}).length
  return { text: count ? count + ' 项未保存 · 草稿仅保存在当前页面内存中' : '没有未保存的更改' }
}

function buildChanges(draft) {
  return Object.values(draft.changes).map(change => {
    const { row, op, raw, path } = change
    const item = { path, op }
    if (op !== 'set') return item
    let value = raw
    const fail = message => { throw new Error((row.label || row.key) + '：' + message) }
    if (row.editor === 'secret' && !raw.trim()) fail('替换密钥不能为空，请填写新密钥或选择「保持不变」。')
    if (row.editor === 'boolean') {
      if (!['true', 'false'].includes(raw)) fail('请选择开启或关闭。')
      value = raw === 'true'
    } else if (row.editor === 'integer' || row.editor === 'number') {
      value = Number(raw)
      if (!raw.trim() || !Number.isFinite(value) || (row.editor === 'integer' && !Number.isInteger(value))) {
        fail(row.editor === 'integer' ? '请输入整数。' : '请输入有效数值。')
      }
    } else if (row.editor === 'json') {
      try {
        value = JSON.parse(raw)
      } catch {
        fail('格式不正确，请输入有效 JSON。')
      }
    }
    item.value = value
    return item
  })
}

function confirmDialog(text) {
  return typeof window !== 'undefined' && typeof window.confirm === 'function' ? window.confirm(text) : true
}

async function load(force = false) {
  // 有草稿或正在保存时沿用上次读取的文件版本，避免把用户正在编辑的行冲掉。
  if (!force && data.value && (dirtyTotal() || busyTotal())) return
  const mine = ++request
  try {
    const payload = await apiGet('/api/configuration')
    if (mine !== request) return
    if (!force && data.value && (dirtyTotal() || busyTotal())) return
    if (data.value) {
      const preserve = id => Boolean(drafts.value[id] || busy.value[id])
      payload.sources = (payload.sources || []).filter(source => !preserve(source.id))
        .concat((data.value.sources || []).filter(source => preserve(source.id)))
      payload.sections = (payload.sections || []).filter(item => !preserve(item.source_id))
        .concat((data.value.sections || []).filter(item => preserve(item.source_id)))
    }
    data.value = payload
    error.value = ''
    ctx?.markRefreshed?.()
  } catch (err) {
    if (mine !== request) return
    error.value = err.message || '配置载入失败'
  }
}

async function reload() {
  if (busyTotal()) return
  if (dirtyTotal() && !confirmDialog('重新载入会放弃当前全部配置草稿，包括尚未保存的密钥替换。继续刷新？')) return
  drafts.value = {}
  messages.value = {}
  await load(true)
}

function cancelSource(source) {
  if (busy.value[source.id]) return
  delete drafts.value[source.id]
  delete messages.value[source.id]
}

async function postConfiguration(body) {
  const response = await fetch('/api/configuration', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Wxbot-Config-Action': '1'
    },
    body: JSON.stringify(body)
  })
  const text = await response.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  return { ok: response.ok, status: response.status, payload: payload || {} }
}

async function saveSource(source) {
  const draft = drafts.value[source.id]
  if (!source || source.status === 'error' || !draft || !Object.keys(draft.changes).length || busy.value[source.id]) return
  let changes
  try {
    changes = buildChanges(draft)
  } catch (err) {
    messages.value[source.id] = { text: err.message, error: true }
    return
  }
  const summary = Object.values(draft.changes)
    .map(change => {
      const action = change.op === 'default' ? '恢复默认' : change.op === 'clear' ? '清空密钥' : '修改'
      return (change.row.label || change.row.key) + '（' + change.row.key + '）：' + action +
        '\n  生效：' + (change.row.effect || '按来源服务的配置规则生效')
    })
    .join('\n')
  const ask = '保存 ' + (source.title || source.id) + '\n\n' + summary +
    '\n\n保存后的生效与重启要求见以上提示。确认保存 ' + changes.length + ' 项更改？'
  if (!confirmDialog(ask)) return
  busy.value[source.id] = true
  delete messages.value[source.id]
  let saved = false
  try {
    const reply = await postConfiguration({
      source: source.id,
      version: draft.version,
      changes,
      acknowledge: true
    })
    if (!reply.ok || !reply.payload.ok) {
      messages.value[source.id] = {
        text: (reply.payload.error || '保存失败') +
          (reply.status === 409 ? '；文件版本已变化，请点击「重新载入配置」刷新后重新编辑。' : ''),
        error: true
      }
    } else {
      delete drafts.value[source.id]
      saved = true
      messages.value[source.id] = {
        text: (reply.payload.message || '已保存') +
          (reply.payload.restart?.length ? '；需重启：' + reply.payload.restart.join('、') : '')
      }
    }
  } catch {
    messages.value[source.id] = { text: '保存请求失败，请检查连接后重试。', error: true }
  } finally {
    delete busy.value[source.id]
  }
  if (saved) await load(true)
}

function pickSection(id) {
  section.value = id
  const pane = document.querySelector('#pane')
  if (pane) pane.scrollTop = 0
}
</script>

<template>
  <Teleport to="#page-tools">
    <input
      id="c-search"
      v-model="search"
      type="text"
      placeholder="搜索配置名称或值"
      aria-label="搜索配置"
    >
  </Teleport>

  <aside id="list">
    <div
      v-for="category in navCategories"
      :key="category.id"
      class="user"
      :class="{ sel: section === category.id }"
      role="button"
      tabindex="0"
      @keydown.enter="pickSection(category.id)"
      @keydown.space.prevent="pickSection(category.id)"
      @click="pickSection(category.id)"
    >
      <div class="nm">{{ category.title }}</div>
      <div class="st">{{ category.count }} 项<template v-if="category.id === 'advanced'"> · 兼容配置</template></div>
    </div>
  </aside>

  <section id="pane">
    <div v-if="!data" class="empty warn">{{ error || '正在载入配置…' }}</div>
    <template v-else>
      <div class="head">
        <h2>{{ paneTitle }}</h2>
        <div class="monitor-note">{{ data.note }}</div>
        <p class="monitor-note">修改后点击保存；生效方式见各项提示。刷新页面会丢失未保存的修改。</p>
        <p v-if="section === 'model'" class="monitor-note">微信消息固定走 wxbot → Butler → 所选模型。切换接入方式后保存，下一请求即用新模型，正在处理的请求继续用原模型；用不到的字段收在高级配置里。</p>
        <div v-if="section === 'contacts'" class="hbnote">
          联系人、监听、角色、心跳、订阅和记忆统一在 <button @click="go('contacts')">联系人</button> 维护。
        </div>
        <button id="c-reload" :disabled="busyTotal() > 0" @click="reload">重新载入配置</button>
        <span class="monitor-source"> 有草稿时会确认放弃更改</span>
        <div v-if="error" class="monitor-note warn">{{ error }}</div>
        <div v-for="(warning, index) in data.warnings || []" :key="'warn-' + index" class="monitor-note warn">{{ warning }}</div>
      </div>

      <template v-for="entry in visibleSections" :key="'sec-' + entry.id">
        <details v-if="entry.advanced" class="config-section">
          <summary>{{ entry.title }}<template v-if="entry.compatibility"> · 未启用 / 兼容配置</template></summary>
          <ConfigField
            v-for="row in entry.rows"
            :key="'f-' + row.key"
            :field="fieldOf(entry.section, row)"
            @update="(field, raw, op) => updateDraft(entry.section, field, raw, op)"
          />
        </details>
        <div v-else class="config-section">
          <h3>{{ entry.title }}<template v-if="entry.compatibility"> · 未启用 / 兼容配置</template></h3>
          <ConfigField
            v-for="row in entry.rows"
            :key="'f-' + row.key"
            :field="fieldOf(entry.section, row)"
            @update="(field, raw, op) => updateDraft(entry.section, field, raw, op)"
          />
        </div>
      </template>

      <div v-if="!visibleSections.length" class="empty">当前分类没有匹配配置，可清空搜索或选择左侧「全部配置」。</div>

      <div class="config-savebar">
        <strong id="c-dirty-count">{{ dirtyCount }} 项未保存</strong>
        <div
          v-for="source in sourceActions"
          :key="'src-' + source.id"
          class="source-actions"
          :class="{
            dirty: Boolean(drafts[source.id]),
            'has-message': Boolean(messages[source.id]),
            'source-error': source.status === 'error'
          }"
        >
          <strong>{{ source.title }}</strong>
          <div class="config-actions">
            <template v-if="source.version && !source.read_only">
              <button
                class="wx"
                :disabled="!(source.status !== 'error' && drafts[source.id] && !busy[source.id])"
                @click="saveSource(source)"
              >{{ source.id === 'directory' ? '保存联系人设置' : '保存此文件' }}</button>
              <button :disabled="!(drafts[source.id] && !busy[source.id])" @click="cancelSource(source)">取消更改</button>
            </template>
            <span class="config-status" :class="{ warn: statusOf(source).error }">
              {{ source.status === 'error' ? source.error : statusOf(source).text }}
            </span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* Hallmark · checked: 2026-10-31 · genre: modern-minimal (inferred)
 * built: the project · redesign: polish · shape: app screen · v2.0.0 */
button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible,
.user:focus-visible { outline: 2px solid var(--wx); outline-offset: 2px; }
button:active:not(:disabled) { background: var(--bg3); }
button:disabled { color: var(--fg3); background: var(--bg2); cursor: not-allowed; }
.config-actions button { white-space: nowrap; }
:deep(.config-editor), :deep(.config-field select) { border-color: var(--fg3); }
</style>
