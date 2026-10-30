<script setup>
import { computed, onMounted, onUnmounted, provide, reactive, ref, watch } from 'vue'
import { activeTab, TABS, go, tabTitle } from './router'
import { apiGet } from './api'
import { readPreference, savePreference } from './prefs'
import ConfigurationView from './views/ConfigurationView.vue'
import ContactsView from './views/ContactsView.vue'
import JobsView from './views/JobsView.vue'
import QueueView from './views/QueueView.vue'
import WorkflowView from './views/WorkflowView.vue'
import TelegramRelayView from './views/TelegramRelayView.vue'

const VIEWS = {
  configuration: ConfigurationView,
  contacts: ContactsView,
  jobs: JobsView,
  queue: QueueView,
  workflow: WorkflowView,
  'telegram-relay': TelegramRelayView
}

const connection = ref({ mode: 'local' })
const listCollapsed = ref(readPreference('listCollapsed', false))
const search = reactive({})
const autoSeconds = ref(0)
const refreshKey = ref(0)
const refreshedAt = ref('等待载入')
let timer = null

provide('logWebCtx', {
  refreshKey,
  search,
  markRefreshed() {
    refreshedAt.value = '最近读取 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }
})

// 外部接入模式下业务页面由对端管理台维护，隐藏本机不承担的业务页。
const hidden = computed(() => {
  const mode = connection.value.mode || 'local'
  return mode === 'local' ? new Set() : new Set(['contacts', 'jobs', 'telegram-relay'])
})

const navGroups = computed(() => {
  const groups = []
  for (const tab of TABS) {
    if (hidden.value.has(tab.id)) continue
    let group = groups.find(item => item.title === tab.group)
    if (!group) {
      group = { title: tab.group, tabs: [] }
      groups.push(group)
    }
    group.tabs.push(tab)
  }
  return groups
})

const title = computed(() => tabTitle(activeTab.value))
const view = computed(() => VIEWS[activeTab.value] || WorkflowView)
// 配置页与转发页用页内筛选，不显示全局搜索框。
const searchHidden = computed(() => activeTab.value === 'configuration' || activeTab.value === 'telegram-relay')
const searchPlaceholder = computed(() => ({
  workflow: '搜索用户 / UID / 消息 ID',
  queue: '筛选本页任务',
  heartbeat: '搜索 Skill 或执行记录'
})[activeTab.value] || '搜索当前记录')
const footText = computed(() => hidden.value.size
  ? '通道管理 · 业务功能请使用对端管理台'
  : 'Butler / wxbot\n运行管理台 · 保存不自动重启')

watch(listCollapsed, value => {
  document.body.classList.toggle('list-collapsed', value)
  document.body.classList.toggle('list-open', !value)
})

watch(autoSeconds, value => {
  clearInterval(timer)
  timer = null
  if (value) timer = setInterval(refresh, value * 1000)
})

watch([connection, activeTab], () => {
  if (hidden.value.has(activeTab.value)) go('configuration')
}, { deep: true })

onMounted(async () => {
  document.body.classList.toggle('list-collapsed', listCollapsed.value)
  document.body.classList.toggle('list-open', !listCollapsed.value)
  try {
    connection.value = await apiGet('/api/connection')
  } catch {
    // 旧服务没有该接口时按本机模式处理。
  }
})

onUnmounted(() => clearInterval(timer))

function refresh() {
  refreshKey.value += 1
}

function toggleList() {
  listCollapsed.value = !listCollapsed.value
  savePreference('listCollapsed', listCollapsed.value)
}

function toggleAuto() {
  autoSeconds.value = autoSeconds.value ? 0 : 15
}

function expand(open) {
  const pane = document.querySelector('#pane')
  if (pane) pane.querySelectorAll('details').forEach(node => { node.open = open })
}
</script>

<template>
  <nav class="primary-nav" aria-label="主导航">
    <div class="brand">
      <span class="brand-mark">管</span>
      <div>微信管家<small>运行管理台</small></div>
    </div>
    <div v-for="group in navGroups" :key="group.title" class="nav-group">
      <h2>{{ group.title }}</h2>
      <button
        v-for="tab in group.tabs"
        :key="tab.id"
        :class="{ on: activeTab === tab.id }"
        :aria-current="activeTab === tab.id ? 'page' : null"
        @click="go(tab.id)"
      >{{ tab.title }}</button>
    </div>
    <div class="nav-foot">{{ footText }}</div>
  </nav>

  <div class="workspace">
    <header>
      <div class="row">
        <h1>{{ title }}</h1>
        <span id="refresh-status" class="muted">{{ refreshedAt }}</span>
      </div>
      <div class="row toolbar">
        <!-- 工作流页自行每秒轮询，同样隐藏列表与自动刷新按钮。 -->
        <button v-if="activeTab !== 'workflow'" id="b-contacts" :aria-expanded="String(!listCollapsed)" @click="toggleList">
          {{ listCollapsed ? '展开列表' : '收起列表' }}
        </button>
        <button @click="refresh">刷新</button>
        <button v-if="activeTab !== 'workflow'" :class="{ on: autoSeconds > 0 }" @click="toggleAuto">
          自动刷新：{{ autoSeconds ? autoSeconds + 's' : '关' }}
        </button>
        <!-- 页面专属按钮由各视图 Teleport 到这里，保持工具栏固定顺序。 -->
        <div id="page-tools" class="page-tools"></div>
        <input
          v-if="!searchHidden"
          id="view-search"
          v-model="search[activeTab]"
          type="search"
          :placeholder="searchPlaceholder"
          aria-label="搜索当前记录"
        >
        <button @click="expand(true)">展开本页</button>
        <button @click="expand(false)">收起本页</button>
      </div>
    </header>
    <main>
      <component :is="view" :tab="activeTab" />
    </main>
  </div>
</template>
