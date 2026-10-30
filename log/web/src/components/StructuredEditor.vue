<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  widget: { type: String, default: 'string-list' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const ALIAS_SOURCES = [['manual', '人工填写'], ['learned', '自动识别'], ['legacy', '历史导入']]
const CONTACT_FIELDS = [
  ['name', '微信会话名称'], ['uid', '唯一用户 ID'], ['label', '显示名称'],
  ['profile', 'Profile'], ['channel_type', '会话类型']
]

const rows = ref([])
const invalid = ref('')
let selfUpdate = false

parse(props.modelValue)

watch(() => props.modelValue, value => {
  if (selfUpdate) return
  parse(value)
})

function parse(text) {
  try {
    const value = JSON.parse(text || '[]')
    if (!Array.isArray(value) || value.some(item => !item || typeof item !== 'object' || Array.isArray(item))) {
      rows.value = []
      invalid.value = '列表数据无效，请重新载入。'
      return
    }
    rows.value = value
    invalid.value = ''
  } catch {
    rows.value = []
    invalid.value = '列表数据无效，请重新载入。'
  }
}

function commit() {
  selfUpdate = true
  emit('update:modelValue', JSON.stringify(rows.value, null, 2))
  nextTick(() => { selfUpdate = false })
}

function textOf(value) {
  return value == null ? '' : String(value)
}

function setField(index, key, value) {
  const row = rows.value[index]
  if (!row) return
  row[key] = value
  commit()
}

function removeRow(index) {
  rows.value.splice(index, 1)
  commit()
}

function addRow() {
  if (props.widget === 'alias-list') {
    rows.value.push({ group: '', member_key: '', name: '', source: 'manual', pending: true })
  } else if (props.widget === 'string-list') {
    rows.value.push('')
  } else {
    rows.value.push({
      name: '', uid: '', profile: 'default', channel_type: 'dm',
      ...(props.widget === 'directory-contacts' ? { listening: false } : {})
    })
  }
  commit()
}

function setString(index, event) {
  rows.value[index] = event.target.value
  commit()
}

function toggleListening(index, event) {
  setField(index, 'listening', Boolean(event.target.checked))
}
</script>

<template>
  <div class="warn" v-if="invalid">{{ invalid }}</div>
  <template v-else>
    <div v-if="widget === 'string-list'" class="list-editor">
      <div v-for="(item, index) in rows" :key="'s' + index" class="row">
        <input type="text" :value="textOf(item)" :disabled="disabled" @input="setString(index, $event)">
        <button :disabled="disabled" @click="removeRow(index)">移除</button>
      </div>
      <button :disabled="disabled" @click="addRow">添加一项</button>
    </div>

    <div v-else-if="widget === 'alias-list'" class="alias-editor">
      <div class="monitor-table-wrap">
        <table class="monitor-table">
          <thead><tr><th>所属群</th><th>群昵称</th><th>成员标识</th><th>来源</th><th>待核对</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="(row, index) in rows" :key="'a' + index">
              <td><input type="text" :value="textOf(row.group)" placeholder="填写所属群" :disabled="disabled" @input="setField(index, 'group', $event.target.value)"></td>
              <td><input type="text" :value="textOf(row.name)" placeholder="填写群昵称" :disabled="disabled" @input="setField(index, 'name', $event.target.value)"></td>
              <td><input type="text" :value="textOf(row.member_key)" placeholder="成员观测标识" :disabled="disabled" @input="setField(index, 'member_key', $event.target.value)"></td>
              <td>
                <select :value="row.source || 'manual'" :disabled="disabled" @change="setField(index, 'source', $event.target.value)">
                  <option v-for="source in ALIAS_SOURCES" :key="source[0]" :value="source[0]">{{ source[1] }}</option>
                </select>
              </td>
              <td>
                <label class="alias-pending">
                  <input type="checkbox" :checked="Boolean(row.pending)" :disabled="disabled" @change="setField(index, 'pending', $event.target.checked)">
                  待核对
                </label>
              </td>
              <td><button type="button" :disabled="disabled" @click="removeRow(index)">移除</button></td>
            </tr>
            <tr v-if="!rows.length"><td colspan="6">暂无群昵称记录</td></tr>
          </tbody>
        </table>
      </div>
      <button type="button" :disabled="disabled" @click="addRow">添加群昵称</button>
      <p class="muted">尚未确定所属群的记录保留“待核对”。这里只维护昵称显示，身份绑定在联系人详情管理。</p>
    </div>

    <div v-else-if="widget === 'directory-contacts'" class="directory-contact-editor monitor-table-wrap">
      <table class="monitor-table">
        <thead><tr><th>微信会话名称</th><th>类型</th><th>监听</th><th>显示名称</th><th>路由信息</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="'d' + index">
            <td><input type="text" :value="textOf(row.name)" :disabled="disabled" @input="setField(index, 'name', $event.target.value)"></td>
            <td>
              <select :value="row.channel_type === 'group' ? 'group' : 'dm'" :disabled="disabled" @change="setField(index, 'channel_type', $event.target.value)">
                <option value="dm">私聊</option>
                <option value="group">群聊</option>
              </select>
            </td>
            <td><input type="checkbox" :checked="Boolean(row.listening)" :disabled="disabled" @change="toggleListening(index, $event)"></td>
            <td><input type="text" :value="textOf(row.label)" :disabled="disabled" @input="setField(index, 'label', $event.target.value)"></td>
            <td>
              <details>
                <summary>高级路由</summary>
                <label>用户 ID<input type="text" :value="textOf(row.uid)" :disabled="disabled" @input="setField(index, 'uid', $event.target.value)"></label>
                <label>Profile<input type="text" :value="textOf(row.profile)" :disabled="disabled" @input="setField(index, 'profile', $event.target.value)"></label>
              </details>
            </td>
            <td><button type="button" :disabled="disabled" @click="removeRow(index)">移除</button></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6">暂无联系人</td></tr>
        </tbody>
      </table>
      <button type="button" :disabled="disabled" @click="addRow">添加联系人 / 群</button>
    </div>

    <div v-else class="contact-editor">
      <div v-for="(contact, index) in rows" :key="'c' + index" class="contact-row">
        <label v-for="field in CONTACT_FIELDS" :key="field[0]">
          {{ field[1] }}
          <select
            v-if="field[0] === 'channel_type'"
            :value="contact.channel_type === 'group' ? 'group' : 'dm'"
            :disabled="disabled"
            @change="setField(index, 'channel_type', $event.target.value)"
          >
            <option value="dm">私聊</option>
            <option value="group">群聊</option>
          </select>
          <input
            v-else
            type="text"
            :value="textOf(contact[field[0]])"
            :disabled="disabled"
            @input="setField(index, field[0], $event.target.value)"
          >
        </label>
        <div class="contact-actions">
          <button :disabled="disabled" @click="removeRow(index)">移除此联系人</button>
        </div>
      </div>
      <button :disabled="disabled" @click="addRow">添加联系人</button>
    </div>
  </template>
</template>
