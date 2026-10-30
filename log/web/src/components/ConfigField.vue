<script setup>
import StructuredEditor from './StructuredEditor.vue'

const props = defineProps({ field: { type: Object, required: true } })
const emit = defineEmits(['update'])

const LIST_WIDGETS = ['directory-contacts', 'alias-list']

function display() {
  const value = props.field.row.value
  return typeof value === 'string' ? (value || '（空）') : JSON.stringify(value, null, 2)
}

function push(raw, op = 'set') {
  emit('update', props.field, raw, op)
}

function onInput(event) {
  push(event.target.value)
}

function onSecretMode(event) {
  push('', event.target.value)
}
</script>

<template>
  <div class="config-field" :class="{ 'config-field-list': LIST_WIDGETS.includes(field.row.widget) }">
    <div>
      <div class="config-label">{{ field.label }}</div>
      <div v-if="field.description" class="monitor-note">{{ field.description }}</div>
      <div v-if="field.effect" class="monitor-source">生效：{{ field.effect }}</div>
    </div>
    <div class="config-control">
      <pre v-if="!field.editable">{{ display() }}</pre>
      <template v-else>
        <template v-if="field.row.editor === 'secret'">
          <div class="monitor-source">{{ field.row.value }} · 原密钥已隐藏</div>
          <select :value="field.mode" :disabled="field.disabled" @change="onSecretMode">
            <option value="keep">保持不变</option>
            <option value="set">替换密钥</option>
            <option value="clear">清空密钥</option>
          </select>
          <input
            class="config-editor"
            type="password"
            autocomplete="new-password"
            placeholder="选择替换后填写新密钥"
            :disabled="field.disabled || field.mode !== 'set'"
            :value="field.mode === 'set' ? field.raw : ''"
            @input="onInput"
          >
        </template>
        <select v-else-if="field.kind === 'select'" class="config-editor" :disabled="field.disabled" :value="field.raw" @change="onInput">
          <option v-for="choice in field.choices" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
        </select>
        <input
          v-else-if="field.kind === 'number'"
          class="config-editor"
          type="number"
          :step="field.step"
          :disabled="field.disabled"
          :value="field.raw"
          @input="onInput"
        >
        <input
          v-else-if="field.kind === 'text'"
          class="config-editor"
          type="text"
          :disabled="field.disabled"
          :value="field.raw"
          @input="onInput"
        >
        <template v-else-if="field.kind === 'structured'">
          <StructuredEditor
            :model-value="field.raw"
            :widget="field.row.widget"
            :disabled="field.disabled"
            @update:model-value="value => push(value)"
          />
          <details>
            <summary>高级 JSON 编辑</summary>
            <textarea
              class="config-editor"
              rows="4"
              spellcheck="false"
              :disabled="field.disabled"
              :value="field.raw"
              @input="onInput"
            ></textarea>
          </details>
        </template>
        <textarea
          v-else
          class="config-editor"
          :rows="field.row.editor === 'json' ? 4 : 2"
          spellcheck="false"
          :disabled="field.disabled"
          :value="field.raw"
          @input="onInput"
        ></textarea>
        <button v-if="field.defaultAvailable" class="config-default" :disabled="field.disabled" @click="push('', 'default')">
          恢复默认
        </button>
        <div v-if="field.draftOp === 'default'" class="monitor-source">待保存：恢复默认值</div>
      </template>
      <div v-if="field.sensitive" class="monitor-source">密钥已隐藏</div>
    </div>
  </div>
</template>
