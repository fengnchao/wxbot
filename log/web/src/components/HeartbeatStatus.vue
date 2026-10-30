<script setup>
import { computed } from 'vue'
import { fullTime } from '../api'
import { hbContact, hbStatus, hbStatusError, query } from '../contactState'

const EVENT_LABELS = {
  scheduler_started: 'Butler 心跳调度启动',
  scheduled: '下次心跳已安排',
  trigger_started: '心跳开始执行',
  trigger_skipped: '本轮跳过',
  contact_selected: '选中联系人',
  hermes_call_started: '开始调用 模型运行时',
  hermes_result: '模型运行时 返回结果',
  push_succeeded: '建议已发送',
  push_failed: '建议发送失败',
  error: '执行错误',
  scheduler_not_started: '调度未启动',
  scheduler_stopping: '调度正在停止',
  scheduler_stopped: '调度已停止',
  manual_trigger_requested: '收到手动触发请求',
  manual_trigger_accepted: 'Butler 已接受手动触发',
  manual_trigger_rejected: '手动触发未执行'
}
const REASONS = {
  no_enabled_contacts: '没有已开启心跳的联系人',
  contact_not_configured: '联系人未配置',
  policy_missing: '联系人尚未保存角色和 Skill 配置',
  policy_unavailable: '角色和 Skill 配置不可读取',
  busy: '已有一轮心跳正在执行',
  start_failed: '无法启动执行'
}

const events = computed(() => {
  const status = hbStatus.value
  if (!status) return []
  const needle = query.value.trim().toLowerCase()
  return (Array.isArray(status.events) ? status.events : []).filter(event =>
    (!event.contact || event.contact === hbContact.value) &&
    (!needle || [event.contact, event.event, event.text, event.detail, event.role_skill]
      .join(' ').toLowerCase().includes(needle)))
})

const nextRun = computed(() => {
  const due = Number(hbStatus.value?.next_run_at)
  return Number.isFinite(due) && due > 0 ? fullTime(due) : '尚未安排'
})

const errors = computed(() => {
  const status = hbStatus.value
  if (!status) return []
  return [
    status.state_error && '调度状态读取失败（' + status.state_error + '）',
    status.audit_error && '审计文件读取失败（' + status.audit_error + '）'
  ].filter(Boolean)
})

function title(event) {
  if (event.event === 'hermes_result') {
    if (event.result === 'none') return '模型运行时 检查完成：没有建议'
    if (event.result === 'suggestion') return '模型运行时 返回了建议'
    if (event.result === 'invalid') return '模型运行时 返回格式无效'
    return '模型运行时 返回'
  }
  if (event.event === 'error') return '执行错误（' + (event.phase || '未知阶段') + '）'
  return EVENT_LABELS[event.event] || event.event || '心跳事件'
}

function meta(event) {
  return [
    event.source && '来源：' + (event.source === 'manual' ? '手动' : '定时'),
    event.contact && '用户：' + event.contact,
    event.role_skill && '角色：' + event.role_skill,
    event.elapsed_ms != null && '耗时：' + event.elapsed_ms + ' ms',
    Array.isArray(event.allowed_skills) && event.allowed_skills.length &&
      '允许技能：' + event.allowed_skills.join('、')
  ].filter(Boolean).join(' · ')
}

function detail(event) {
  return event.text || event.detail ||
    (event.next_run_at ? '下次触发：' + fullTime(Number(event.next_run_at)) : (REASONS[event.reason] || ''))
}

function dateText(value) {
  if (!value) return '-'
  if (typeof value === 'string') {
    const stamp = Date.parse(value)
    return Number.isNaN(stamp) ? value : fullTime(stamp / 1000)
  }
  return fullTime(value)
}
</script>

<template>
  <div class="hbstatus">
    <template v-if="hbStatus">
      <h2>心跳运行记录 <span class="summary">已开启 {{ hbStatus.enabled_contacts || 0 }} 位 · 下次计划：{{ nextRun }}</span></h2>
      <details>
        <summary>展开最近 {{ events.length }} 条执行记录</summary>
        <div v-if="errors.length" class="warn">{{ errors.join('；') }}</div>
        <div v-for="(event, index) in events" :key="'hb-' + index" class="hbevent">
          <div class="evt"><b>{{ title(event) }}</b><time>{{ dateText(event.at) }}</time></div>
          <div v-if="meta(event)" class="meta">{{ meta(event) }}</div>
          <div v-if="detail(event)" class="detail">{{ detail(event) }}</div>
        </div>
        <div v-if="!events.length" class="empty">暂无心跳事件记录；Butler 调度启动或下一轮触发后会显示过程。</div>
      </details>
    </template>
    <template v-else>
      <h2>心跳运行记录</h2>
      <div class="warn">读取运行记录失败：{{ hbStatusError || '未知错误' }}</div>
    </template>
  </div>
</template>
