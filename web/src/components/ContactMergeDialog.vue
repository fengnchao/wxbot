<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { closeDialog, contactSave, dialog, dialogBusy, dialogError, userRequest } from '../contactState'

const payload = dialog.value.payload
const shell = ref(null)
const preview = ref(null)
const loading = ref(false)
const acknowledged = ref(false)
let disposed = false
onUnmounted(() => { disposed = true })
onMounted(() => {
  if (typeof shell.value?.showModal === 'function') shell.value.showModal()
  else shell.value?.setAttribute('open', '')
  refresh()
})

async function refresh() {
  preview.value = null
  acknowledged.value = false
  loading.value = true
  dialogError.value = ''
  try {
    const result = await userRequest('/api/contacts/merge-preview?' + new URLSearchParams(payload))
    if (!disposed) preview.value = result
  } catch (error) {
    if (!disposed) dialogError.value = error.message || String(error)
  } finally {
    if (!disposed) loading.value = false
  }
}

async function confirm() {
  if (!preview.value || !acknowledged.value || dialogBusy.value) return
  dialogBusy.value = true
  try {
    await contactSave({ action: 'merge', version: preview.value.version,
      id: payload.target_id, source_id: payload.source_id, preview_version: preview.value.preview_version })
  } catch (error) {
    if (!disposed) {
      dialogError.value = (error.message || String(error)) + '；请重新预览后确认。'
      preview.value = null
      acknowledged.value = false
    }
  } finally {
    if (!disposed) dialogBusy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="shell" class="user-dialog" id="contact-merge-dialog" @cancel.prevent="closeDialog">
      <div class="user-dialog-title"><h2>确认人物身份合并</h2>
        <button type="button" @click="closeDialog" :disabled="dialogBusy">关闭</button></div>
      <p class="user-error" role="alert">{{ dialogError }}</p>
      <p v-if="loading">正在读取双方档案与记忆版本…</p>
      <form v-else-if="preview" @submit.prevent="confirm" class="user-form">
        <p>将「{{ preview.source.name }}」的全部身份并入「{{ preview.target.name }}」，保留目标人物。</p>
        <section v-for="side in ['source', 'target']" :key="side" class="user-section">
          <h3>{{ side === 'source' ? '并入来源' : '保留目标' }}：{{ preview[side].name }}</h3>
          <p>{{ preview[side].bindings.length }} 条身份，{{ preview[side].conversations.length }} 个窗口，{{ preview[side].memory_count }} 条记忆</p>
          <p>默认角色：{{ preview[side].policy?.role_skill || '未配置' }}</p>
          <ul><li v-for="window in preview[side].conversations" :key="window.id">
            窗口：{{ window.name }}，{{ window.enabled ? '启用' : '停用' }}，{{ window.policy?.role_skill || '继承默认或未配置' }}
          </li><li v-for="binding in preview[side].bindings" :key="binding.binding_id">
            {{ binding.channel_type === 'group' ? '群身份' : '私聊身份' }}：{{ binding.contact }} / {{ binding.nickname }}
          </li></ul>
        </section>
        <details v-if="preview.conflicts.length"><summary>记忆冲突（保留全部来源）</summary>
          <p v-for="(item, index) in preview.conflicts" :key="index">{{ item.key }}：{{ item.value }}（{{ item.source_label }}）</p>
        </details>
        <p>{{ preview.rules }}</p>
        <label class="user-check"><input type="checkbox" v-model="acknowledged" required>已核对双方是同一个人及全部影响范围；合并无法在此撤销</label>
        <button type="submit" :disabled="!acknowledged || dialogBusy">确认合并</button>
      </form>
      <button v-else type="button" @click="refresh" :disabled="dialogBusy">重新预览</button>
    </dialog>
  </Teleport>
</template>
