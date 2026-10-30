// 工作流页与旧版 messages.js 共用同一套流转文案和分组规则。
// 事件阶段的措辞必须与队列详情一致，避免同一事件在两处显示不同说法。

export const FLOW_STAGE_LABELS = {
  wxbot_received: 'wxbot 确认收件入库', wxbot_inbox: '进入收件队列', wxbot_merge: '连续消息合并',
  wxbot_model: '模型工作线程领取', wxbot_butler: 'wxbot 请求 Butler', butler_received: 'Butler 确认收到',
  butler_session: 'Butler 会话锁', hermes_request: 'Butler 请求 模型运行时', hermes_generating: '模型运行时 生成回复',
  hermes_tool: '模型运行时 工具执行', hermes_status: '模型运行时 过程事件', hermes_approval: '模型运行时 等待审批',
  hermes_result: '模型运行时 完整结果', butler_action: 'Butler 行动执行', butler_result: 'Butler 结果就绪',
  wxbot_result: 'wxbot 完整回复入发件箱', wxbot_outbox: '回复分句入队', wechat_submitted: '微信已按回车',
  wechat_delivery: '微信分句发送', wxbot_reply_mode: '群回复方式决策', telegram_media: 'Telegram 图片准备',
  telegram_received: 'Telegram 机器人收件', telegram_butler: 'Butler 确认收件', telegram_news: '新闻投递回执',
  butler_identity: '身份解析', butler_memory: '相关记忆召回', butler_context: '群公共上下文',
  wxbot_group_context: '群消息归档', wxbot_group_decision: '本地群回复决策', wechat_mention: '微信提及对象核验'
}

export const WF_DECISIONS = {
  direct: '主动请求', cooldown: '冷却中', budget: '预算已用完', random: '普通插话',
  emoji: '表情回复', silent: '未抽中 / 静默'
}

export const FLOW_STATUS_LABELS = {
  ok: '完成', started: '已开始，等待确认', accepted: '接口已接受', waiting: '等待中',
  running: '执行中', completed: '执行结束', failed: '失败', error: '失败', blocked: '已阻塞',
  uncertain: '结果不确定', unconfirmed: '未记录 / 未确认', not_started: '未提交', pending: '待发送',
  sending: '键入中', confirming: '发送确认中', sent: '已确认发送', skipped: '已跳过 / 丢弃',
  text: '文字回复', emoji: '表情回复', none: '静默（不回复）', preparing: '图片准备中',
  media_failed: '图片准备失败', awaiting_bot: '等待机器人收件', ready: '已就绪',
  archived: '已归档 / 静默', confirmed: '身份已确认', observed: '身份待核对',
  unknown: '身份待绑定', ambiguous: '身份待核对', ...WF_DECISIONS
}

export const WF_STATUS = {
  unbatched: '等待合并', ready: '等待提交', processing: '处理中', waiting_delivery: '回复已就绪',
  pending: '等待发送', sending: '分批输入中', confirming: '等待气泡确认', sent: '已确认发送',
  blocked: '已阻断', uncertain: '结果不确定', waiting_blocker: '等待旧任务释放', discarded: '已丢弃',
  model_failed: '模型失败已结束', no_reply: '本轮无需回复', archived: '已归档 / 静默',
  received: 'Butler 已收件，等待新闻调度', rejected: '已拒绝', not_submitted: '新闻未提交',
  cancelled: '已取消', skipped: '已跳过', preparing: '图片准备中',
  media_failed: '图片准备失败', awaiting_bot: '等待机器人收件'
}

export const WF_IDENTITIES = {
  confirmed: '已确认', observed: '待核对', unknown: '待绑定', ambiguous: '待核对', disabled: '已停用'
}

export const WF_MENTIONS = {
  pending: '等待选择', selecting: '选择中', object_verified: '提及对象已核验',
  fallback_plain: '未提及，已转纯正文', selection_blocked: '提及选择已阻断'
}

const WF_COLORS = ['#72b4ff', '#bb9aff', '#51d4b1', '#f0bc76', '#f18db0']

export const p2 = n => String(n).padStart(2, '0')

export function hm(t) {
  const date = new Date(t * 1000)
  return p2(date.getHours()) + ':' + p2(date.getMinutes())
}

export function stageLabel(stage) {
  return FLOW_STAGE_LABELS[stage] || stage
}

export function statusLabel(status) {
  return FLOW_STATUS_LABELS[status] || status
}

export function colorOf(message) {
  const text = message.uid + '|' + (message.members || []).join('|')
  let hash = 0
  for (const char of text) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return WF_COLORS[hash % WF_COLORS.length]
}

/** 卡片预览只保留 20 个字素，避免长消息撑破服务节点。 */
export function workflowExcerpt(value) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  const characters = typeof Intl.Segmenter === 'function'
    ? Array.from(new Intl.Segmenter('zh-CN', { granularity: 'grapheme' }).segment(text), part => part.segment)
    : Array.from(text)
  return characters.length > 20 ? characters.slice(0, 20).join('') + '…' : text
}

export function workflowErrorSummary(message) {
  if (!message.error) return ''
  if (/timeout|timed out|routing|超时/i.test(message.error)) {
    return message.terminal ? '模型连接超时，本轮已结束' : '模型连接超时，等待处理'
  }
  if (message.status === 'model_failed') return '模型执行失败，本轮已结束'
  if (message.status === 'uncertain') return '发送结果待核实，请查看队列'
  return message.terminal ? '本轮处理异常，已结束' : '处理异常，请查看详情'
}

/** 与旧版 messages.js 同名的流转分组：把同名事件折叠成一行。 */
export function groupFlowEvents(events) {
  const groups = new Map()
  const pending = new Map()
  let occurrence = 0
  for (const event of events) {
    const base = [event.stage, event.tool || '', event.tool_call_id || '', event.part_seq || '',
      event.delivery_id || '', event.attempt || ''].join(':')
    let key = base
    if (event.stage === 'hermes_tool' && !event.tool_call_id) {
      const active = pending.get(base) || []
      if (['started', 'running'].includes(event.status)) {
        key = base + ':occurrence:' + occurrence++
        if (active.length) active.forEach(id => { groups.get(id).ambiguous = true })
        groups.set(key, { ...event, firstTs: event.ts, ambiguous: !!active.length })
        active.push(key)
        pending.set(base, active)
        continue
      }
      if (active.length === 1 && !groups.get(active[0]).ambiguous) key = active[0]
      else key = base + ':event:' + occurrence++
      if (['completed', 'ok', 'failed', 'error', 'blocked', 'uncertain'].includes(event.status)) active.shift()
      pending.set(base, active)
    }
    if (!groups.has(key)) {
      groups.set(key, { ...event, start: event.ts, firstTs: event.ts })
    } else {
      const row = groups.get(key)
      const first = row.firstTs
      Object.assign(row, event)
      row.firstTs = first
      if (event.elapsed_ms == null && event.ts != null && first != null) {
        row.elapsed_ms = Math.max(0, (event.ts - first) * 1000)
      }
    }
  }
  return [...groups.values()].sort((a, b) => (a.firstTs ?? Infinity) - (b.firstTs ?? Infinity))
}

// 后端阶段保持精确；多个阶段共用同一个物理服务节点。
export function workflowService(stage) {
  return ['wxbot', 'inbox', 'butler', 'model', 'butler', 'outbox', 'wxbot', 'wxbot', 'telegram', 'butler'][stage] || 'butler'
}

export function workflowEventEdge(event) {
  if (event.stage === 'telegram_butler') return 'telegram'
  if (event.stage === 'telegram_news' && event.status === 'sending') return 'enqueue'
  if (event.stage === 'telegram_news' && event.status === 'sent') return 'send'
  if (event.stage === 'wxbot_inbox') return 'receive'
  if (['wxbot_butler', 'butler_received'].includes(event.stage)) return 'dispatch'
  if (event.stage === 'hermes_request') return 'request'
  if (event.stage === 'hermes_result' && ['ok', 'completed'].includes(event.status)) return 'result'
  if (event.stage === 'wxbot_result' && event.status === 'ok') return 'enqueue'
  if (event.stage === 'wechat_submitted' ||
    (event.stage === 'wechat_delivery' && ['sending', 'confirming', 'sent'].includes(event.status))) return 'send'
  return ''
}

/** 倒计时按最近一次成功读取的服务端时间推进；断线时冻结。 */
export function deadlineText(at, serverNow) {
  const remaining = Math.max(0, Math.ceil(Number(at) - serverNow))
  return remaining > 0 ? remaining + ' 秒' : '等待调度执行'
}
