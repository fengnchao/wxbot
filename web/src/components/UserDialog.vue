<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { fullTime } from '../api'
import {
  audit, auditOffset, closeDialog, contactRequest, data, dialog, dialogBusy, dialogError,
  load, loadAudit, loadMemory, openMerge, memory, memoryOffset, memoryQuery, submitDialog, userRequest
} from '../contactState'

const shell = ref(null)
const payload = dialog.value.payload
const view = ref(dialog.value.kind)
const form = reactive({
  contact: payload?.contact || '',
  nickname: payload?.nickname || '',
  enabled: Boolean(payload?.enabled),
  memberKey: '',
  memoryKey: '',
  memoryValue: ''
})
const targets = ref([])
const linkQuery = ref('')
const deleting = ref(null)
const editingKey = ref(false)

const memoryItems = computed(() => {
  const needle = memoryQuery.value.trim().toLowerCase()
  return (memory.value?.items || []).filter(item =>
    !needle || (item.key + ' ' + item.value).toLowerCase().includes(needle))
})
const memoryPage = computed(() =>
  memoryItems.value.slice(memoryOffset.value, memoryOffset.value + 20))
const member = computed(() => memory.value?.binding || null)

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
})

function close() {
  closeDialog()
}

function userLabel(row) {
  if (!row) return ''
  return row.channel_type === 'group' ? row.contact + '－' + row.nickname : row.nickname
}

async function readAvatar(input) {
  const file = input.files?.[0]
  if (!file) return ''
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 512 * 1024) {
    throw new Error('头像须为 PNG、JPEG 或 WebP，最大 512 KiB、400 万像素')
  }
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('头像读取失败'))
    reader.readAsDataURL(file)
  })
}

function submitBinding() {
  submitDialog(async () => {
    const avatarInput = shell.value?.querySelector('#binding-avatar')
    const avatar = avatarInput?.files?.length ? await readAvatar(avatarInput) : ''
    await userRequest('/api/users', {
      action: 'update',
      binding_id: payload.binding_id,
      version: payload.version,
      contact: form.contact.trim(),
      nickname: form.nickname.trim(),
      enabled: form.enabled,
      ...(avatar ? { avatar } : {}),
      ...(form.memberKey.trim() ? { member_key: form.memberKey.trim() } : {})
    })
    close()
    await load()
  })
}

function openUserLink() {
  view.value = 'link'
}

function submitFind() {
  submitDialog(async () => {
    const result = await userRequest('/api/users?' +
      new URLSearchParams({ query: linkQuery.value.trim(), limit: '50' }))
    targets.value = (result.rows || []).filter(target =>
      target.binding_id !== payload.binding_id && target.user_id !== payload.user_id)
  })
}

function submitPreview(target) {
  openMerge(payload.user_id, target.user_id)
}

function openMemoryEdit(item = null) {
  editingKey.value = Boolean(item)
  form.memoryKey = item?.key || ''
  form.memoryValue = item?.value || ''
  view.value = 'memory-edit'
}

function openMemoryDelete(item) {
  deleting.value = item
  view.value = 'memory-delete'
}

function submitMemory() {
  const current = memory.value
  if (!current) return
  submitDialog(async () => {
    if (current.contact_id) {
      data.value = await contactRequest({
        action: 'memory_set',
        id: current.contact_id,
        version: data.value.version,
        memory_version: current.version,
        key: form.memoryKey.trim(),
        value: form.memoryValue
      })
    } else {
      await userRequest('/api/users', {
        action: 'memory_set',
        binding_id: current.binding.binding_id,
        version: current.version,
        key: form.memoryKey.trim(),
        value: form.memoryValue
      })
    }
    await loadMemory(current.binding.binding_id)
    view.value = 'memory'
  })
}

function submitDelete() {
  const current = memory.value
  const item = deleting.value
  if (!current || !item) return
  submitDialog(async () => {
    if (current.contact_id) {
      data.value = await contactRequest({
        action: 'memory_delete',
        id: current.contact_id,
        version: data.value.version,
        memory_version: current.version,
        key: item.key
      })
    } else {
      await userRequest('/api/users', {
        action: 'memory_delete',
        binding_id: current.binding.binding_id,
        version: current.version,
        key: item.key
      })
    }
    await loadMemory(current.binding.binding_id)
    view.value = 'memory'
  })
}

function openAudit() {
  auditOffset.value = 0
  view.value = 'audit'
  loadAudit()
}

function auditPage(step) {
  auditOffset.value = Math.max(0, auditOffset.value + step)
  loadAudit()
}

function backToMemory() {
  view.value = 'memory'
}

function atText(value) {
  if (!value) return '-'
  return typeof value === 'string' ? value : fullTime(value)
}
</script>

<template>
  <Teleport to="body">
    <dialog id="user-dialog" ref="shell" class="user-dialog" @cancel.prevent="close">
      <div class="user-dialog-title">
        <h2>{{ dialog.title }}</h2>
        <button type="button" id="user-dialog-close" aria-label="关闭" @click="close">关闭</button>
      </div>
      <p id="user-dialog-error" class="user-error" role="alert">{{ dialogError }}</p>
      <div id="user-dialog-content">
        <form v-if="view === 'binding'" id="user-binding-form" class="user-form" @submit.prevent="submitBinding">
          <p><code>{{ payload.user_id }}</code></p>
          <label>群名／私聊会话名<input v-model="form.contact" name="contact" required maxlength="200"></label>
          <label>群昵称／私聊昵称<input v-model="form.nickname" name="nickname" required maxlength="200"></label>
          <label class="user-check"><input v-model="form.enabled" name="enabled" type="checkbox">启用此绑定</label>
          <p v-if="payload.status === 'observed'" class="user-warning">此记录尚待核对。确认身份后保存，才允许使用个人记忆。</p>
          <p v-if="payload.observed_member_keys?.length" class="monitor-note">
            已观测成员 ID：{{ payload.observed_member_keys.join(' / ') }}
          </p>
          <label>人工确认的头像观测 ID（可选）<input v-model="form.memberKey" name="member_key" maxlength="128" placeholder="仅填写已核对身份的历史 member_key"></label>
          <p class="monitor-note">新增观测 ID 会成为该群身份的识别依据，请先核对工作流中的成员。原有参考保留。</p>
          <label>补充头像参考（可选）<input id="binding-avatar" name="avatar" type="file" accept="image/png,image/jpeg,image/webp"></label>
          <p class="monitor-note">PNG / JPEG / WebP，最大 512 KiB、400 万像素；保存时移除元数据。</p>
          <div class="row">
            <button type="submit" :disabled="dialogBusy">保存绑定</button>
            <button type="button" id="user-link" @click="openUserLink">手工绑定为同一用户</button>
          </div>
        </form>

        <template v-else-if="view === 'link'">
          <p>来源：{{ userLabel(payload) }}<br><code>{{ payload.user_id }}</code></p>
          <form id="user-link-find" class="user-form" @submit.prevent="submitFind">
            <label>查找目标绑定<input v-model="linkQuery" name="query" placeholder="输入昵称、群名或固定 ID" required></label>
            <button type="submit" :disabled="dialogBusy">查找</button>
          </form>
          <div id="user-link-targets">
            <template v-if="targets.length">
              <p class="monitor-note">最多显示 50 个；可用固定 ID 缩小范围。</p>
              <p v-for="target in targets" :key="'t-' + target.binding_id">
                {{ userLabel(target) }}，<code>{{ target.user_id }}</code>
                <button @click="submitPreview(target)">预览共享范围</button>
              </p>
            </template>
            <p v-else>没有可关联的目标，请调整搜索。</p>
          </div>
        </template>

        <template v-else-if="view === 'memory'">
          <p v-if="!memory">正在读取记忆…</p>
          <template v-else>
            <p>
              <strong>{{ userLabel(member) }}</strong><br>
              用户 <code>{{ member.user_id }}</code><br>
              绑定 <code>{{ member.binding_id }}</code>
            </p>
            <p class="monitor-note">
              当前共享记忆范围：<code>{{ member.memory_owner || member.user_id }}</code>，版本 {{ memory.version }}。已关联的其他绑定也能使用这里的记忆。
            </p>
            <div class="row">
              <button id="user-memory-add" @click="openMemoryEdit()">新增记忆</button>
              <button id="user-audit" @click="openAudit">修改记录</button>
              <input id="user-memory-search" v-model="memoryQuery" type="search" aria-label="搜索记忆" placeholder="搜索记忆">
            </div>
            <div class="monitor-table-wrap">
              <table class="monitor-table">
                <thead><tr><th>记忆 key</th><th>内容</th><th>更新</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="item in memoryPage" :key="'mi-' + item.key">
                    <td>{{ item.key }}</td>
                    <td class="preview">{{ item.value }}<small v-if="item.source_label">来源：{{ item.source_label }}</small></td>
                    <td>{{ atText(item.updated) }}</td>
                    <td>
                      <button @click="openMemoryEdit(item)">修正</button>
                      <button @click="openMemoryDelete(item)">删除</button>
                    </td>
                  </tr>
                  <tr v-if="!memoryPage.length"><td colspan="4">此范围暂无匹配记忆。</td></tr>
                </tbody>
              </table>
            </div>
            <div class="pagination">
              <button :disabled="memoryOffset === 0" @click="memoryOffset = Math.max(0, memoryOffset - 20)">上一页</button>
              <span>{{ memoryItems.length ? memoryOffset + 1 : 0 }} 至 {{ Math.min(memoryOffset + 20, memoryItems.length) }} / {{ memoryItems.length }}</span>
              <button :disabled="memoryOffset + 20 >= memoryItems.length" @click="memoryOffset += 20">下一页</button>
            </div>
          </template>
        </template>

        <form v-else-if="view === 'memory-edit'" id="user-memory-form" class="user-form" @submit.prevent="submitMemory">
          <h3>{{ editingKey ? '修正记忆' : '新增记忆' }}</h3>
          <label>记忆 key<input v-model="form.memoryKey" name="key" required maxlength="200" :readonly="editingKey"></label>
          <label>内容<textarea v-model="form.memoryValue" name="value" required rows="6"></textarea></label>
          <p class="monitor-note">保存后会更新共享范围，并使后续模型会话使用新的记忆版本。</p>
          <div class="row">
            <button type="submit" :disabled="dialogBusy">保存记忆</button>
            <button type="button" id="user-memory-back" @click="backToMemory">返回</button>
          </div>
        </form>

        <template v-else-if="view === 'memory-delete' && deleting">
          <h3>删除记忆 {{ deleting.key }}</h3>
          <p class="pre">{{ deleting.value }}</p>
          <p>该内容将从当前共享范围移除，后续模型不再召回。修改记录会保留。</p>
          <div class="row">
            <button id="user-memory-delete-confirm" :disabled="dialogBusy" @click="submitDelete">确认删除</button>
            <button id="user-memory-back" @click="backToMemory">返回</button>
          </div>
        </template>

        <template v-else-if="view === 'audit'">
          <h3>修改记录，{{ userLabel(member) }}</h3>
          <button id="user-memory-back" @click="backToMemory">返回记忆</button>
          <div v-if="!audit" class="empty">正在读取修改记录…</div>
          <template v-else>
            <div class="monitor-table-wrap">
              <table class="monitor-table">
                <thead><tr><th>时间</th><th>操作</th><th>来源与内容</th></tr></thead>
                <tbody>
                  <tr v-for="(row, index) in audit.rows" :key="'au-' + index">
                    <td>{{ atText(row.at) }}</td>
                    <td>{{ row.action }}</td>
                    <td class="preview"><pre>{{ JSON.stringify(row.details, null, 2) }}</pre></td>
                  </tr>
                  <tr v-if="!audit.rows.length"><td colspan="3">暂无修改记录。</td></tr>
                </tbody>
              </table>
            </div>
            <div class="pagination">
              <button :disabled="auditOffset === 0" @click="auditPage(-20)">上一页</button>
              <span>{{ auditOffset + (audit.rows?.length || 0) }} / {{ audit.total }}</span>
              <button :disabled="auditOffset + 20 >= audit.total" @click="auditPage(20)">下一页</button>
            </div>
          </template>
        </template>
      </div>
    </dialog>
  </Teleport>
</template>
