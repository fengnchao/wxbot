<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { apiGet, apiPost, fullTime } from '../api'

defineProps({ tab: { type: String, default: 'knowledge-template' } })
const ctx = inject('logWebCtx', null)

// 三层的名字要和接口里的 source 对上：覆盖层坏了时真正生效的是内置模板。
const SOURCE_LABELS = {
  override: '自定义覆盖层',
  plugin: '插件内置模板',
  builtin: '程序内置默认'
}
const CONFIRM_HEADER = 'X-Wxbot-Knowledge-Action'

const info = ref(null)          // 服务端读到的原文、来源、版本与已保存的摘要
const draft = ref('')           // 编辑中的全文
const baseline = ref('')        // 最近一次保存/读取的内容，用来判断有没有改过
const failure = ref('')
const status = ref({ text: '', error: false })
const busy = ref(false)
let request = 0

const dirty = computed(() => Boolean(info.value) && draft.value !== baseline.value)
const summary = computed(() => info.value?.summary || null)
const errors = computed(() => info.value?.errors || [])
const sourceLabel = computed(() => SOURCE_LABELS[info.value?.source] || '读取中')
const canReset = computed(() => Boolean(info.value) && info.value.override !== 'absent')
const versionLabel = computed(() => String(info.value?.version || '').slice(0, 10) || '—')
const modifiedLabel = computed(() => {
  const at = Number(info.value?.modified_at || 0)
  return at > 0 ? fullTime(at) : '未知'
})
const statusText = computed(() => {
  if (busy.value) return '正在处理…'
  if (status.value.text) return status.value.text
  return dirty.value ? '有未保存的修改，保存后下一次提炼生效' : '与已保存的模板一致'
})

onMounted(() => load())
watch(() => ctx?.refreshKey?.value, () => load())

async function load(force = false) {
  // 正在编辑时不清空草稿：工具栏的刷新不能把人写了一半的模板冲掉。
  if (!force && (dirty.value || busy.value)) return
  const mine = ++request
  try {
    const payload = await apiGet('/api/knowledge/template')
    if (mine !== request) return
    info.value = payload
    draft.value = payload.content || ''
    baseline.value = draft.value
    failure.value = ''
    ctx?.markRefreshed?.()
  } catch (err) {
    if (mine !== request) return
    info.value = null
    failure.value = err.message || '知识模板载入失败'
  }
}

function confirmDialog(text) {
  return typeof window !== 'undefined' && typeof window.confirm === 'function' ? window.confirm(text) : true
}

async function reload() {
  if (busy.value) return
  if (dirty.value && !confirmDialog('重新载入会放弃当前未保存的模板修改，继续？')) return
  await load(true)
}

async function submit(action) {
  if (busy.value || !info.value) return
  if (action === 'save' && !dirty.value) return
  busy.value = true
  status.value = { text: '', error: false }
  try {
    const reply = await apiPost('/api/knowledge/template', {
      action,
      content: draft.value,
      version: info.value.version,
      acknowledge: true
    }, CONFIRM_HEADER)
    await load(true)
    const counts = reply.summary
      ? '：' + reply.summary.node_types.length + ' 个节点目录、' + reply.summary.kinds.length +
        ' 个分类、' + reply.summary.rules + ' 条追加规则'
      : ''
    const backup = reply.backup ? '；旧模板备份在 ' + reply.backup : ''
    status.value = {
      text: (action === 'validate' ? '校验通过' + counts : (reply.message || '已保存')) + backup,
      error: false
    }
  } catch (err) {
    // 400 会带逐行错误：拼在状态行里，改的时候不用来回翻。
    const lines = (err.payload?.errors || [])
      .map(item => (item.line ? '第 ' + item.line + ' 行：' : '') + item.message)
    status.value = {
      text: err.message + (lines.length ? '；' + lines.join('；') : ''),
      error: true
    }
  } finally {
    busy.value = false
  }
}

async function save() {
  if (!confirmDialog('保存知识模板？\n\n保存后：新建的用户 vault 按新目录建骨架，下一次提炼按新分类与规则执行。'
    + '\n已有节点里的历史事实不会被重写，也不会删除任何知识。')) return
  await submit('save')
}

async function reset() {
  if (!confirmDialog('恢复内置模板？\n\n只删除自定义覆盖层 data/knowledge/template.md，vault 里的知识一条都不会丢。')) return
  await submit('reset')
}
</script>

<template>
  <aside id="list">
    <div class="tpl-side">
      <h2>生效模板</h2>
      <p class="tpl-side-source">{{ sourceLabel }}</p>
      <p class="tpl-side-meta">修改于 {{ modifiedLabel }} · 版本 {{ versionLabel }}</p>

      <template v-if="summary">
        <h3>节点目录 {{ summary.node_types.length }}</h3>
        <ul class="tpl-side-list">
          <li v-for="item in summary.node_types" :key="'tpl-nt-' + item.key">
            <code>{{ item.key }}</code><span>{{ item.label }}</span>
          </li>
        </ul>
        <h3>分类 {{ summary.kinds.length }}</h3>
        <ul class="tpl-side-list">
          <li v-for="item in summary.kinds" :key="'tpl-kind-' + item.key">
            <code>{{ item.key }}</code><span>{{ item.label }}</span>
          </li>
        </ul>
        <h3>追加规则 {{ summary.rules }}</h3>
        <p class="tpl-side-note">内置的安全规则不可删，模板里只写追加部分。</p>
      </template>
      <p v-else class="tpl-side-note warn">覆盖层解析失败，当前按内置模板运行。</p>
    </div>
  </aside>

  <section id="pane">
    <div class="head">
      <h2>知识图谱模板</h2>
      <div v-if="info" class="monitor-grid">
        <span class="chip">生效来源 <b>{{ sourceLabel }}</b></span>
        <span class="chip">节点目录 <b>{{ summary ? summary.node_types.length : 0 }}</b></span>
        <span class="chip">分类 <b>{{ summary ? summary.kinds.length : 0 }}</b></span>
        <span class="chip">追加规则 <b>{{ summary ? summary.rules : 0 }}</b></span>
      </div>
      <p class="monitor-note">
        模板决定新建用户知识图谱的目录骨架、事实分类、索引分区与提炼口径。保存后下一次记录或提炼立即生效；
        已有节点里的历史事实不会被重写。
      </p>
      <p v-if="info" class="monitor-source">
        覆盖层：{{ info.path }}
        <template v-if="info.active_path && info.source !== 'override'"> · 当前生效：{{ info.active_path }}</template>
      </p>
      <div class="tpl-head-actions">
        <button :disabled="busy" @click="reload">重新载入</button>
        <span class="monitor-source">有未保存修改时会先确认</span>
      </div>
      <div v-if="errors.length" class="tpl-errors" role="alert">
        <p>覆盖层没有通过校验，当前仍按内置模板运行：</p>
        <ul>
          <li v-for="(item, index) in errors" :key="'tpl-err-' + index">
            {{ item.line ? '第 ' + item.line + ' 行：' : '' }}{{ item.message }}
          </li>
        </ul>
      </div>
      <p v-if="failure" class="monitor-note warn">{{ failure }}</p>
    </div>

    <div v-if="!info" class="empty">
      {{ failure || '正在读取知识模板…' }}
      <div class="tpl-empty-actions">
        <button :disabled="busy" @click="reload">重新读取</button>
      </div>
    </div>

    <template v-else>
      <label class="tpl-label" for="tpl-editor">模板 Markdown</label>
      <p class="monitor-note">
        「节点目录」「分类」各加一行即可扩展；「提炼规则」只能追加。保存前可以先点「校验模板」看解析结果。
      </p>
      <textarea
        id="tpl-editor"
        v-model="draft"
        class="tpl-editor"
        spellcheck="false"
        :disabled="busy"
        aria-describedby="tpl-status"
      ></textarea>

      <div class="config-savebar tpl-savebar">
        <strong>{{ dirty ? '有未保存的修改' : '没有未保存的修改' }}</strong>
        <div class="config-actions">
          <button :disabled="busy || !draft.trim()" @click="submit('validate')">校验模板</button>
          <button class="wx" :disabled="busy || !dirty" @click="save">保存模板</button>
          <button :disabled="busy || !canReset" @click="reset">恢复内置模板</button>
        </div>
        <span id="tpl-status" class="config-status" :class="{ warn: status.error }" aria-live="polite">
          {{ statusText }}
        </span>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* Hallmark · checked: 2026-11-02 · genre: modern-minimal (inferred)
 * built: the project · shape: app screen · v2.0.0 */
.tpl-side { padding: 8px; }
.tpl-side h2 { margin: 0 0 4px; font-size: 14px; text-wrap: balance; }
.tpl-side h3 {
  display: flex; justify-content: space-between; gap: 8px;
  margin: 16px 0 8px; font-size: 12px; font-weight: 500; color: var(--fg2);
}
.tpl-side-source { margin: 0; font-size: 12px; color: var(--fg); }
.tpl-side-meta,
.tpl-side-note { margin: 4px 0 0; font-size: 11px; line-height: 1.6; color: var(--fg3); }
.tpl-side-note.warn { color: var(--warn); }
.tpl-side-list { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.tpl-side-list li {
  display: flex; gap: 8px; align-items: baseline; min-width: 0;
  font-size: 11.5px; color: var(--fg2);
}
.tpl-side-list code { flex: none; font-size: 11px; color: var(--fg3); }
.tpl-side-list span { overflow-wrap: anywhere; }
.tpl-head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
.tpl-errors {
  margin: 8px 0 0; padding: 8px 12px; border: 1px solid var(--warn);
  border-left-width: 3px; border-radius: 8px; background: var(--bg2); color: var(--warn);
}
.tpl-errors p { margin: 0 0 4px; font-size: 12px; }
.tpl-errors ul { margin: 0; padding-left: 16px; font-size: 12px; line-height: 1.7; }
.tpl-label { display: block; margin: 16px 0 8px; font-size: 12px; color: var(--fg2); }
.tpl-editor {
  display: block; width: 100%; min-height: 52vh; resize: vertical; tab-size: 2;
  padding: 16px; /* 边框用带令牌的亮阶：渲染门禁要求输入框边缘对背景达到 3:1。 */
  border: 1px solid var(--line-strong); border-radius: 10px;
  background: var(--bg2); color: var(--fg);
  font: 12.5px/1.7 "Cascadia Mono", Consolas, monospace;
}
.tpl-editor:focus-visible { outline: 2px solid var(--wx); outline-offset: 1px; }
/* 禁用时同时换底色、字色与光标，不只靠降低透明度。 */
.tpl-editor:disabled { background: var(--bg3); color: var(--fg3); cursor: not-allowed; }
.tpl-savebar { margin-top: 16px; }
#pane button:active:not(:disabled) { background: var(--bg3); }
.tpl-empty-actions { display: flex; justify-content: center; margin-top: 12px; }
@media (max-width: 900px) {
  .tpl-editor { min-height: 46vh; }
}
</style>
