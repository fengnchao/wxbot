// 联系人页的共享状态与请求封装：弹窗、草稿与筛选放在模块级，切标签页不丢。
import { ref } from 'vue'
import { apiGet, apiPost } from './api'

export const data = ref(null)
export const error = ref('')
export const activeId = ref('')
export const section = ref('details')
export const kind = ref('')
export const category = ref('chats')
export const statusFilter = ref('')
export const issueFilter = ref('')
export const detailTab = ref('overview')
export const busy = ref(false)
export const query = ref('')

export const aliasDraft = ref(null)
export const aliasVersion = ref(0)

export const hbStatus = ref(null)
export const hbContact = ref('')
export const hbStatusError = ref('')
export const hbShown = ref(false)

export const dialog = ref(null)
export const dialogError = ref('')
export const dialogBusy = ref(false)
export const skills = ref([])
export const memory = ref(null)
export const memoryOffset = ref(0)
export const memoryQuery = ref('')
export const audit = ref(null)
export const auditOffset = ref(0)

let request = 0
let dialogEpoch = 0

async function readJson(response) {
  const text = await response.text()
  try {
    return text ? JSON.parse(text) : null
  } catch {
    return null
  }
}

export async function contactRequest(payload) {
  const options = payload === undefined
    ? { headers: { Accept: 'application/json' } }
    : {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Wxbot-Contact-Action': '1'
        },
        body: JSON.stringify(payload)
      }
  const response = await fetch('/api/contacts', options)
  const result = await readJson(response)
  if (!response.ok) {
    throw new Error(((result && result.error) || '联系人操作失败') +
      (response.status === 409 ? '；请刷新并重新核对修改。' : ''))
  }
  return result
}

export async function userRequest(path, payload) {
  const options = payload === undefined
    ? { headers: { Accept: 'application/json' } }
    : {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Wxbot-User-Action': '1'
        },
        body: JSON.stringify(payload)
      }
  const response = await fetch(path, options)
  const result = await readJson(response)
  if (!response.ok) throw new Error((result && result.error) || '操作失败（HTTP ' + response.status + '）')
  return result
}

export async function load() {
  const mine = ++request
  try {
    const payload = await contactRequest()
    if (mine !== request) return
    data.value = payload
    error.value = ''
    if (!(payload.rows || []).some(row => row.id === activeId.value)) activeId.value = payload.rows[0]?.id || ''
  } catch (err) {
    if (mine !== request) return
    error.value = err.message || String(err)
  }
}

export function pick(id) {
  activeId.value = id
  section.value = 'details'
  hbShown.value = false
  detailTab.value = 'overview'
}

export function openMerge(sourceId, targetId) {
  openDialog('merge', '确认人物身份合并', { source_id: sourceId, target_id: targetId })
}

export function openDialog(nextKind, title, payload = null) {
  closeDialog()
  dialog.value = { kind: nextKind, title, payload }
  return dialogEpoch
}

export function closeDialog() {
  dialogEpoch += 1
  dialog.value = null
  dialogError.value = ''
  dialogBusy.value = false
  skills.value = []
  memory.value = null
  memoryQuery.value = ''
  memoryOffset.value = 0
  audit.value = null
  auditOffset.value = 0
}

export function sameEpoch(epoch) {
  return epoch === dialogEpoch
}

export async function submitDialog(operation) {
  if (dialogBusy.value) return
  dialogBusy.value = true
  dialogError.value = ''
  try {
    await operation()
  } catch (err) {
    dialogError.value = err.message || String(err)
  } finally {
    dialogBusy.value = false
  }
}

export async function contactSave(payload) {
  data.value = await contactRequest({ version: data.value.version, ...payload })
  closeDialog()
  error.value = ''
}

export async function saveAliases() {
  if (busy.value || !aliasDraft.value) return
  const rows = aliasDraft.value.map(row => ({ ...row }))
  const version = aliasVersion.value
  busy.value = true
  error.value = ''
  try {
    data.value = await contactRequest({ action: 'aliases', version, aliases: rows })
    aliasDraft.value = null
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    busy.value = false
  }
}

export async function loadStatus(row) {
  hbContact.value = row.conversations[0]?.name || ''
  hbShown.value = true
  try {
    hbStatus.value = await apiGet('/api/heartbeat-status?limit=30')
    hbStatusError.value = ''
  } catch (err) {
    hbStatus.value = null
    hbStatusError.value = err.message || String(err)
  }
}

export async function triggerHeartbeat(name) {
  const ask = '立即检查并可能向「' + name + '」发送一次心跳建议？'
  if (!window.confirm(ask)) return
  try {
    const result = await apiPost('/api/heartbeat-trigger', { contact: name })
    if (!result.ok) throw new Error(result.error || '触发失败')
    error.value = '已提交心跳请求'
  } catch (err) {
    error.value = err.message || String(err)
  }
}

export async function loadStatusSilently() {
  try {
    hbStatus.value = await apiGet('/api/heartbeat-status?limit=30')
    hbStatusError.value = ''
  } catch (err) {
    hbStatus.value = null
    hbStatusError.value = err.message || String(err)
  }
}

export async function loadMemory(bindingId) {
  const epoch = openDialog('memory', '用户记忆')
  try {
    const path = bindingId.startsWith('person:')
      ? '/api/contacts/memory?' + new URLSearchParams({ id: bindingId.slice(7) })
      : '/api/users/memory?' + new URLSearchParams({ binding_id: bindingId })
    const result = await userRequest(path)
    if (!sameEpoch(epoch)) return
    memory.value = result
    memoryOffset.value = 0
    memoryQuery.value = ''
  } catch (err) {
    if (sameEpoch(epoch)) dialogError.value = err.message || String(err)
  }
}

export function nextMemoryPage(step) {
  memoryOffset.value = Math.max(0, memoryOffset.value + step)
}

export async function loadAudit() {
  const epoch = dialogEpoch
  try {
    const scope = memory.value.contact_id
      ? { id: memory.value.contact_id }
      : { binding_id: memory.value.binding.binding_id }
    const result = await userRequest(
      (memory.value.contact_id ? '/api/contacts/audit?' : '/api/users/audit?') +
      new URLSearchParams({ ...scope, offset: String(auditOffset.value), limit: '20' })
    )
    if (!sameEpoch(epoch)) return
    audit.value = result
  } catch (err) {
    if (sameEpoch(epoch)) dialogError.value = err.message || String(err)
  }
}
