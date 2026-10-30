/**
 * 无浏览器冒烟测试：用 jsdom 加载构建产物，确认 Vue 壳与已迁移页面能真正渲染。
 * 只读：所有 fetch 均由本地固定数据应答，不连接日志服务、不发送微信消息。
 * 运行：npm run smoke（需要先 npm run build）
 */
import { readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { JSDOM } from 'jsdom'

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, '..', 'dist')

const bundles = readdirSync(join(dist, 'assets')).filter(name => /^index-.*\.js$/.test(name))
if (!bundles.length) throw new Error('缺少构建产物：先执行 npm run build')

const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
  url: 'http://127.0.0.1/app?tab=telegram-relay',
  pretendToBeVisual: true
})
for (const key of ['window', 'document', 'navigator', 'location', 'history', 'localStorage',
  'HTMLElement', 'Element', 'Node', 'Event', 'CustomEvent', 'MutationObserver', 'getComputedStyle',
  'SVGElement', 'ShadowRoot', 'DocumentFragment', 'HTMLInputElement', 'HTMLSelectElement',
  'HTMLTextAreaElement']) {
  // Node 21+ 把 navigator 等声明为只读全局，保留可用的原生实现即可。
  try {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: dom.window[key] })
  } catch {
    /* 只读全局保持原样 */
  }
}
globalThis.requestAnimationFrame = callback => setTimeout(callback, 0)
globalThis.cancelAnimationFrame = id => clearTimeout(id)
// Teleport / 过渡在 update 阶段会做 instanceof Document 等判断，补齐 jsdom 构造器。
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!/^[A-Z]/.test(key) || key in globalThis) continue
  try {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: dom.window[key] })
  } catch {
    /* 只读全局保持原样 */
  }
}

const payloads = {
  '/api/connection': { mode: 'local', local_butler: true, business_tools: true, note: '' },
  '/api/jobs': {
    count: 3, active: 1, paused: 1, error: 0, done: 1,
    users: [
      {
        uid: 'alice', uid_display: 'Alice', name: 'Alice', count: 2, active: 1, paused: 1, error: 0,
        jobs: [
          {
            job_id: 'job-1', name: '每日新闻推送', profile: 'Alice', uid: 'alice', uid_key: 'alice',
            ui_state: 'active', schedule: '每天 09:00', deliver: 'Alice', uid_source: 'profile',
            no_agent: true, next_run_at: '2026-10-31T01:00:00+00:00',
            can_delete: true, delete_version: 3, prompt: '把今天的新闻摘要发给我'
          },
          {
            job_id: 'job-2', name: '午间问候', profile: 'Alice', uid: 'alice', uid_key: 'alice',
            ui_state: 'paused', schedule: '每周一 12:00', deliver: 'Alice', uid_source: 'profile',
            script: 'greet.py', repeat: '每周', can_delete: true, delete_version: 1
          }
        ]
      },
      {
        uid: 'global', uid_display: '', name: '全局任务', count: 1, active: 0, paused: 0, error: 0,
        jobs: [
          {
            job_id: 'job-3', name: '群发通知', profile: 'Butler', uid: '', uid_key: '',
            ui_state: 'done', schedule: '2026-10-01 10:00', deliver: '全部用户',
            uid_source: 'script-profile', no_agent: true, scope: 'global',
            push_type: 2, message_type: 1, last_status: 'sent',
            can_delete: true, delete_version: 2
          }
        ]
      }
    ]
  },
  '/api/queue': {
    read_only: true, status: 'ok', error: '', actions_enabled: true, failure_timeout_seconds: 180,
    counts: {
      unbatched: 2, pending_sessions: 0,
      batches: { ready: 1, processing: 0, done: 3 },
      outbox: { pending: 1, blocked: 1, sent: 5 }
    },
    pages: {
      inbox: { total: 1, offset: 0, limit: 50, has_more: false },
      batches: { total: 1, offset: 0, limit: 50, has_more: false },
      rounds: { total: 1, offset: 0, limit: 50, has_more: false }
    },
    contacts: [{
      contact: 'Alice', unbatched: 2, batches: { ready: 1 }, outbox: { pending: 1, blocked: 1 },
      reason: {
        code: 'blocked', message: '本轮回复发送失败，等待重试或整轮超时结束',
        record_kind: 'outbox', record_id: 'o1', state: 'blocked', error: '窗口未就绪',
        actions: ['retry', 'sent', 'skip'], finished_at: 1700000000, discard_at: 1700000180
      }
    }],
    inbox: [{
      id: 'i1', contact: 'Alice', state: 'unbatched', characters: 12,
      preview: '在吗？帮我查一下天气', created_at: 1700000000, actions: []
    }],
    batches: [{
      id: 'b1', contact: 'Alice', state: 'ready', characters: 12, preview: '在吗？帮我查一下天气',
      created_at: 1700000000, part_count: 2, sent_parts: 0, attempts: 1, actions: []
    }],
    outbox: [],
    rounds: [{
      id: 'reply:b1', contact: 'Alice', state: 'blocked', display_state: 'blocked', preview: '好的，稍等',
      sent_parts: 0, part_count: 2, error: '', created_at: 1700000000, discard_at: 1700000180,
      parts: [{
        id: 'o1', contact: 'Alice', state: 'blocked', part_seq: 1, part_count: 2, characters: 5,
        preview: '好的，稍等', actions: ['retry', 'sent', 'skip'], error: ''
      }]
    }],
    events: [{ seq: 1, at: 1700000000, contact: 'Alice', action: 'failed', reason: '窗口未就绪' }],
    telegram: {
      status: 'ok', error: '', counts: { sent: 2 },
      page: { total: 1, offset: 0, limit: 50, has_more: false },
      rows: [{
        id: 'tg:1:9', contact: 'Telegram · 888', uid: '888', state: 'sent', preview: '频道新闻',
        error: '', reason: '', created_at: 1700000000, received_at: 1700000010, targets: 'Alice',
        deliveries: [{ id: 1, contact: 'Alice', part: 1, state: 'sent', reason: '', updated: 1700000020 }]
      }]
    }
  },
  '/api/configuration': {
    read_only: false, runtime_verified: false, at: 1700000000,
    note: '按来源文件保存修改；保存不等于运行服务已加载。页面逐项标明生效方式，不自动重启任何服务。密钥原值不会回显。',
    warnings: [],
    connection: { mode: 'local', business_tools: true, local_butler: true },
    sources: [
      {
        id: 'wxbot', title: 'wxbot 配置', path: 'config.wxbot.toml', status: 'ok',
        version: 'v-wx-1', error: '', modified_at: null, read_only: false
      },
      {
        id: 'butler', title: 'Butler 配置', path: 'config.butler.toml', status: 'ok',
        version: 'v-bt-1', error: '', modified_at: null, read_only: false
      }
    ],
    sections: [
      {
        id: 'wxbot.butler', title: 'wxbot · butler', source_id: 'wxbot', source: 'config.wxbot.toml',
        rows: [
          {
            key: 'wxbot.butler.command_prefix', value: '/', origin: 'file', sensitive: false,
            path: ['butler', 'command_prefix'], label: '指令前缀',
            description: '群聊中触发机器人的前缀。', editor: 'string', widget: 'string',
            choices: null, editable: true, effect: '保存后需自行重启 wxbot', default_available: true
          },
          {
            key: 'wxbot.butler.poll_interval', value: 3, origin: 'file', sensitive: false,
            path: ['butler', 'poll_interval'], label: '轮询间隔',
            description: '轮询消息间隔（秒）。', editor: 'integer', widget: 'integer',
            choices: null, editable: true, effect: '保存后需自行重启 wxbot', default_available: true
          }
        ]
      },
      {
        id: 'butler.agent', title: 'Butler · agent', source_id: 'butler', source: 'config.butler.toml',
        rows: [{
          key: 'butler.agent.provider', value: 'hermes', origin: 'file', sensitive: false,
          path: ['agent', 'provider'], label: '模型运行时',
          description: 'codex=本地 Codex，hermes=Hermes 服务。', editor: 'string', widget: 'string',
          choices: ['codex', 'hermes'], editable: true, effect: '保存后需自行重启 Butler', default_available: false
        }]
      },
      {
        id: 'butler.contacts', title: 'Butler · contacts', source_id: 'butler', source: 'config.butler.toml',
        rows: [{
          key: 'butler.contacts.list',
          value: [{ name: 'Alice', uid: 'alice', profile: 'default', channel_type: 'dm' }],
          origin: 'file', sensitive: false, path: ['contacts', 'list'], label: '联系人列表',
          description: '统一联系人数据库。', editor: 'json', widget: 'contacts',
          choices: null, editable: true, effect: '保存后立即用于后续角色/心跳检查', default_available: false
        }]
      },
      {
        id: 'wxbot.typing', title: '微信输入与分句（代码固定规则）', source: 'typing.py',
        rows: [{
          key: 'wxbot.typing.input_method', value: '分批剪贴板粘贴', origin: 'code',
          editable: false, sensitive: false
        }]
      }
    ]
  },
  '/api/contacts': {
    active: true, version: 3, total: 2,
    rows: [
      {
        id: 'alice', kind: 'person', name: 'Alice', enabled: true, avatar: '', historical_names: [],
        conversations: [{
          id: 'conv-dm', name: 'Alice', channel_type: 'dm', enabled: true, listening: true,
          subscriptions: [1], uid: 'alice', profile: 'default', label: '', session_key: '',
          needs_route: false, policy: { role_skill: 'assistant', allowed_skills: ['news'], heartbeat_enabled: true }
        }],
        memberships: [{
          binding_id: 'b-group-1', contact: '产品群', nickname: '小A', enabled: true,
          identity_confirmed: false, user_id: 'alice', version: 2, channel_type: 'group',
          status: 'observed', observed_member_keys: ['mk-1']
        }],
        bindings: [{ binding_id: 'b-dm-1', contact: 'Alice', nickname: 'Alice', channel_type: 'dm', enabled: true, version: 1 }],
        memory_count: 2, policy: null, memory_conflicts: []
      },
      {
        id: 'group-1', kind: 'group', name: '产品群', enabled: true, avatar: '',
        conversations: [{
          id: 'group-1', name: '产品群', channel_type: 'group', enabled: true, listening: true,
          subscriptions: [], needs_route: false
        }],
        memberships: [{
          binding_id: 'b-group-1', contact: '产品群', nickname: '小A', enabled: true,
          identity_confirmed: true, user_id: 'alice', version: 2, channel_type: 'group'
        }],
        bindings: [], memory_count: 0, policy: null
      }
    ],
    settings: { bot: { mention_names: ['机器人'] }, wechat: { main_window: { listen_all: false } } },
    aliases: [{ group: '产品群', member_key: 'mk-1', name: '小A', source: 'learned', pending: true }]
  },
  '/api/groups': {
    message_types: [], contacts: [],
    news: {
      schedule: '每日 08:00', note: '保存后下次新闻任务生效。',
      categories: [{ id: 'tech', label: '科技', description: '科技与数码' }, { id: 'society', label: '社会' }],
      sources: [{ id: 'chinanews', label: '中新网', description: '' }],
      settings: { categories: ['tech'], sources: ['chinanews'], count: 5 },
      latest: { date: '2026-10-30', status: 'sent', article_count: 5, sent: 2 },
      version: 'n1'
    }
  },
  '/api/heartbeat-status': {
    events: [{
      event: 'push_succeeded', at: 1700000000, contact: 'Alice', source: 'manual',
      role_skill: 'assistant', elapsed_ms: 1200, text: '建议已发送'
    }],
    next_run_at: 1700003600, enabled_contacts: 1, state_error: '', audit_error: ''
  },
  '/api/workflow': {
    status: 'ok', read_only: true, at: 1700000000, backend: 'codex',
    model: { provider: 'codex', label: 'Codex', model: 'gpt-5', via_butler: true },
    counts: { active: 2, inbox: 2, model: 1, outbox: 1, issues: 1, closed_issues: 1, sent: 1, telegram: 3 },
    sources: [{ name: 'wxbot', status: 'ok', truncated: false }, { name: 'Butler', status: 'ok', truncated: true }],
    active_more: false, history_more: false, error: '',
    messages: [
      {
        kind: 'batch', id: 'b1', contact: 'Alice', uid: 'alice', label: 'Alice', group: false, members: [],
        request_id: 'req-abcdef123456', inbox_ids: ['i1'], user_id: 'user-alice', binding_id: 'b-dm-1',
        identity_status: 'confirmed', memory_count: 2, context_count: 0, context_from: 0, context_to: 0,
        decision: 'direct', mention_stage: '', preview: '帮我查一下明天的天气', reply_preview: '', error: '',
        at: 1699999995, updated_at: 1700000000, order: 1, terminal: false, scope: 'active',
        stage: 3, status: 'processing', attempts: 1, part_count: 0, sent_parts: 0,
        retry_at: null, discard_at: null, can_delete: false, delete_version: '', events_truncated: false,
        events: [
          { node: 1, stage: 'wxbot_inbox', status: 'ok', ts: 1699999980, key: 'e1' },
          { node: 2, stage: 'butler_identity', status: 'confirmed', ts: 1699999985, key: 'e2' },
          { node: 2, stage: 'butler_memory', status: 'ok', ts: 1699999986, key: 'e3' },
          { node: 3, stage: 'hermes_request', status: 'started', ts: 1699999990, key: 'e4' },
          { node: 3, stage: 'hermes_tool', status: 'started', tool: 'news_search', ts: 1699999995, key: 'e5' }
        ]
      },
      {
        kind: 'batch', id: 'b2', contact: '产品群', uid: 'group-1', label: '产品群', group: true, members: ['小A', '小B'],
        request_id: 'req-group-2', inbox_ids: ['i2'], user_id: '', binding_id: 'b-group-1',
        identity_status: 'observed', memory_count: 0, context_count: 3, context_from: 1, context_to: 3,
        decision: 'random', mention_stage: 'fallback_plain',
        preview: '群里讨论发布计划', reply_preview: '收到，我来整理', error: '窗口未就绪',
        at: 1699999901, updated_at: 1699999990, order: 2, terminal: false, scope: 'issues',
        stage: 6, status: 'blocked', attempts: 2, part_count: 2, sent_parts: 0,
        retry_at: 1700000100, discard_at: 1700000180, can_delete: false, delete_version: '', events_truncated: false,
        events: [
          { node: 1, stage: 'wxbot_inbox', status: 'ok', ts: 1699999901, key: 'f1' },
          { node: 2, stage: 'butler_received', status: 'ok', ts: 1699999902, key: 'f2' },
          { node: 2, stage: 'butler_memory', status: 'ok', ts: 1699999903, key: 'f3' },
          { node: 3, stage: 'hermes_result', status: 'ok', ts: 1699999950, key: 'f4' },
          { node: 5, stage: 'wxbot_outbox', status: 'ok', ts: 1699999951, key: 'f5' },
          { node: 6, stage: 'wechat_delivery', status: 'blocked', ts: 1699999990, key: 'f6', error: '窗口未就绪' }
        ]
      },
      {
        kind: 'push', id: 'push:p1', contact: 'Alice', uid: 'alice', label: 'Alice', group: false, members: [],
        request_id: '', inbox_ids: [], user_id: '', binding_id: '', identity_status: '',
        preview: '新闻推送正文', reply_preview: '', error: '',
        at: 1699999800, updated_at: 1699999800, order: 3, terminal: true, scope: 'complete',
        stage: 6, status: 'sent', attempts: 0, part_count: 0, sent_parts: 0,
        retry_at: null, discard_at: null, can_delete: true, delete_version: 'v3', events_truncated: false,
        events: [{ node: 6, stage: 'wechat_delivery', status: 'sent', ts: 1699999799, key: 'g1' }]
      }
    ]
  },
  '/api/skills': {
    skills: [
      { name: 'assistant', description: '通用助手', category: '角色', tags: ['butler-role'] },
      { name: 'news', description: '新闻检索', category: '工具', tags: [] }
    ]
  },
  '/api/telegram-relay': {
    settings: {
      enabled: true, include_text: true, include_images: false, include_source: true, include_time: true,
      window_title: 'Telegram', bot_username: 'demo_bot', bot_id: 123456,
      poll_interval: 30, album_quiet_seconds: 4, max_album_wait: 90,
      admin_contacts: ['管理员甲'],
      channels: [{ key: 'news1', name: '新闻频道', username: 'news_channel', chat_id: 1001, enabled: true }],
      desktop: { window: 'Telegram' }
    },
    version: 'v1',
    note: '保存由现有服务下次读取生效，不自动重启。',
    runtime: {
      state: 'running', phase: '扫描频道', at: 1700000000,
      counts: { forwarded: 3 }, channels: [{ key: 'news1', name: '新闻频道', phase: '空闲' }]
    }
  }
}

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, 'http://127.0.0.1')
  const method = String(init.method || 'GET').toUpperCase()
  if (url.pathname === '/api/configuration' && method === 'POST') {
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ok: true, message: '已保存', restart: ['wxbot'] })
    }
  }
  if (url.pathname === '/api/contacts' && method === 'POST') {
    const body = JSON.parse(init.body || '{}')
    const current = payloads['/api/contacts']
    const next = { ...current, version: current.version + 1 }
    if (body.action === 'aliases') next.aliases = body.aliases
    return { ok: true, status: 200, text: async () => JSON.stringify(next) }
  }
  if (url.pathname === '/api/workflow-stream') {
    const id = url.searchParams.get('id')
    return {
      ok: true, status: 200,
      json: async () => ({
        id, available: true, cursor: 2, reset: false, more: false,
        events: [
          { seq: 1, type: 'summary_delta', text: '正在整理天气' },
          { seq: 2, type: 'tool', tool: 'news_search', status: 'running' }
        ]
      })
    }
  }
  if (url.pathname === '/api/workflow-content') {
    const id = url.searchParams.get('id')
    return {
      ok: true, status: 200,
      json: async () => ({
        id, status: 'ok', kind: id.startsWith('push:') ? 'push' : 'batch',
        text: '帮我查一下明天的天气', reply_text: '明天有小雨，记得带伞。'
      })
    }
  }
  if (url.pathname === '/api/workflow-delete' && method === 'POST') {
    return { ok: true, status: 200, json: async () => ({ ok: true, removed: 1 }) }
  }
  const data = payloads[url.pathname]
  if (!data) return { ok: false, status: 404, text: async () => '{"error":"not found"}' }
  return { ok: true, status: 200, text: async () => JSON.stringify(data), json: async () => data }
}

const problems = []
const { warn, error } = console
console.warn = (...args) => { problems.push('WARN ' + args.join(' ')); warn(...args) }
console.error = (...args) => { problems.push('ERROR ' + args.join(' ')); error(...args) }

await import(pathToFileURL(join(dist, 'assets', bundles[0])).href)
await new Promise(resolve => setTimeout(resolve, 150))

const text = selector => (document.querySelector(selector)?.textContent || '').replace(/\s+/g, ' ')
const failures = []
const expect = (ok, message) => { if (!ok) failures.push(message) }

const navButtons = [...document.querySelectorAll('.nav-group button')].map(node => node.textContent.trim())
expect(navButtons.length === 6, '导航应渲染 6 个标签，实际 ' + navButtons.length + '：' + navButtons.join('/'))
expect(navButtons.includes('Telegram 转发'), '导航缺少「Telegram 转发」')

const pane = text('#pane')
for (const phrase of ['Telegram 频道转发', '监听与内容', '频道列表', '新闻频道', 'Telegram 控件校准',
  '保存设置', '运行与队列状态', '扫描频道']) {
  expect(pane.includes(phrase), '主区域缺少「' + phrase + '」')
}
expect(text('#list').includes('频道 → 现有机器人'), '左栏说明未渲染')

const channelInput = document.querySelector('tbody input[type=text]')
expect(channelInput?.value === 'news1', '频道表格未绑定草稿值，实际 ' + (channelInput?.value ?? 'null'))

const contactButton = [...document.querySelectorAll('.nav-group button')].find(node => node.textContent.trim() === '联系人')
contactButton?.click()
await new Promise(resolve => setTimeout(resolve, 150))

const contactList = text('#list')
for (const phrase of ['联系人', '新增联系人 / 群', '筛选', '新闻推送设置', '全局监听设置',
  '群昵称与待核对别名', 'Alice', '1 个所属群']) {
  expect(contactList.includes(phrase), '联系人左栏缺少「' + phrase + '」')
}
const contactPane = text('#pane')
for (const phrase of ['Alice', '会话与投递目的地', '监听开启', '订阅 新闻',
  '会话覆盖角色：assistant', '自动心跳开启', '所属群与群昵称', '产品群', '小A',
  '待核对', 'b-group-1', '共享记忆', '2 条', '基本资料', '默认角色与 Skill',
  '关联已有群成员', '新增所属群', '新增私聊目的地', '心跳运行记录']) {
  expect(contactPane.includes(phrase), '联系人详情缺少「' + phrase + '」')
}

document.querySelector('#contact-status')?.click()
await new Promise(resolve => setTimeout(resolve, 100))
const statusPane = text('#pane')
for (const phrase of ['已开启 1 位', '建议已发送', '展开最近 1 条执行记录']) {
  expect(statusPane.includes(phrase), '心跳运行记录缺少「' + phrase + '」')
}

document.querySelector('#contact-news')?.click()
await new Promise(resolve => setTimeout(resolve, 100))
const newsPane = text('#pane')
for (const phrase of ['新闻推送设置', '新闻类型 · 可多选', '科技', '每日新闻条数',
  '保存新闻设置', '最近执行']) {
  expect(newsPane.includes(phrase), '新闻设置缺少「' + phrase + '」')
}

document.querySelector('#contact-aliases')?.click()
await new Promise(resolve => setTimeout(resolve, 100))
const aliasPane = text('#pane')
for (const phrase of ['群昵称与待核对别名', '所属群', '群昵称', '成员标识', '添加群昵称']) {
  expect(aliasPane.includes(phrase), '群昵称设置缺少「' + phrase + '」')
}
expect(document.querySelectorAll('#pane .alias-editor').length === 1, '群昵称表格未渲染')

document.querySelector('#contact-create')?.click()
await new Promise(resolve => setTimeout(resolve, 100))
const contactDialog = document.querySelector('dialog.user-dialog')
for (const phrase of ['新增联系人 / 群', '微信窗口名称', '监听与心跳默认关闭']) {
  expect((contactDialog?.textContent || '').includes(phrase), '新增联系人弹窗缺少「' + phrase + '」')
}
document.querySelector('#user-dialog-close')?.click()
await new Promise(resolve => setTimeout(resolve, 50))
expect(!document.querySelector('dialog.user-dialog'), '关闭后弹窗未移除')

const contactFilter = document.querySelector('#contact-filter')
contactFilter.value = 'pending'
contactFilter.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
expect(document.querySelectorAll('#list .contact-row').length === 1, '待补充资料筛选应只保留 Alice，实际 '
  + document.querySelectorAll('#list .contact-row').length)
contactFilter.value = ''
contactFilter.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
expect(document.querySelectorAll('#list .contact-row').length === 2, '清除筛选后应恢复 2 行')

// 定时任务页：左栏归属、卡片行、删除按钮与「显示已完成」开关
const jobsButton = [...document.querySelectorAll('.nav-group button')].find(node => node.textContent.trim() === '定时任务')
jobsButton?.click()
await new Promise(resolve => setTimeout(resolve, 150))

const navText = text('#list')
for (const phrase of ['全部归属', 'Alice', '全局任务', '隐藏已完成 1']) {
  expect(navText.includes(phrase), '定时任务左栏缺少「' + phrase + '」')
}
const jobsPane = text('#pane')
for (const phrase of ['每日新闻推送', '午间问候', '每天 09:00', '按 Profile 归属', 'no_agent',
  'script greet.py', '该组的任务全部已完成']) {
  expect(jobsPane.includes(phrase), '定时任务主区域缺少「' + phrase + '」')
}
expect(!jobsPane.includes('群发通知'), '已完成任务默认应隐藏')
expect(document.querySelectorAll('#pane .jcard').length === 2, '默认可见卡片数应为 2')
expect(document.querySelectorAll('#pane .jcard .discard').length === 2, '卡片缺少删除按钮')

const doneButton = document.querySelector('#page-tools button')
expect(doneButton?.textContent.trim() === '显示已完成', '页首缺少「显示已完成」按钮')
doneButton?.click()
await new Promise(resolve => setTimeout(resolve, 50))
expect(text('#pane').includes('群发通知'), '开启后仍未显示已完成任务')
expect(doneButton?.textContent.trim() === '隐藏已完成', '按钮文案未切换为「隐藏已完成」')

const searchInput = document.querySelector('#view-search')
expect(searchInput?.placeholder === '搜索当前记录', '定时任务搜索框占位符不符')
searchInput.value = '午间'
searchInput.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
const filtered = text('#pane')
expect(filtered.includes('午间问候'), '搜索后未保留匹配任务')
expect(!filtered.includes('每日新闻推送'), '搜索后未过滤不匹配任务')

// 收发队列页：会话侧栏、状态筛选、原因卡、三类表格与事件记录
const queueButton = [...document.querySelectorAll('.nav-group button')].find(node => node.textContent.trim() === '收发队列')
queueButton?.click()
await new Promise(resolve => setTimeout(resolve, 150))

expect(text('#list').includes('全部会话') && text('#list').includes('Alice'), '队列左栏缺少会话')
expect(text('#list').includes('待合并'), '队列左栏缺少待合并计数')
const queuePane = text('#pane')
for (const phrase of ['收发队列 · 全部会话', '全队列待合并', '异常块', '待处理', '异常待核对', '历史记录',
  '本轮回复发送失败', '微信收件（含已合并）', '模型批次', '回复整轮 / 主动推送', '失败与恢复记录',
  'Telegram 收件 / 新闻转发', 'Telegram · 888']) {
  expect(queuePane.includes(phrase), '队列主区域缺少「' + phrase + '」')
}
expect(document.querySelectorAll('#pane .monitor-table').length === 4, '队列表格数量不符：'
  + document.querySelectorAll('#pane .monitor-table').length)
expect(document.querySelectorAll('#pane .queue-actions button').length >= 3, '异常任务缺少核对按钮')
const stateSelect = document.querySelector('#page-tools select')
expect(stateSelect?.value === 'all', '页首缺少队列状态筛选，实际 ' + (stateSelect?.value ?? 'null'))
expect([...stateSelect.options].length === 14, '状态筛选项数量不符')

// 配置管理页：分类计数、页内搜索、结构化编辑器与草稿保存
const configButton = [...document.querySelectorAll('.nav-group button')].find(node => node.textContent.trim() === '配置管理')
configButton?.click()
await new Promise(resolve => setTimeout(resolve, 150))

expect(document.querySelectorAll('#list .user').length === 7, '配置左栏应为 7 个分类，实际 '
  + document.querySelectorAll('#list .user').length)
const configList = text('#list')
for (const phrase of ['基础连接', '微信收发', '模型后端', '联系人与策略', '日志', '高级配置', '全部参数']) {
  expect(configList.includes(phrase), '配置左栏缺少「' + phrase + '」')
}
const configPane = text('#pane')
for (const phrase of ['基础连接', '指令前缀', '轮询间隔', '模型运行时', '修改后点击保存',
  '重新载入配置', '0 项未保存']) {
  expect(configPane.includes(phrase), '配置主区域缺少「' + phrase + '」')
}
expect(!configPane.includes('分批剪贴板粘贴'), '代码固定规则分区应隐藏在「高级配置」外')
const configSearch = document.querySelector('#c-search')
expect(configSearch?.placeholder === '搜索配置名称或值', '页首缺少配置搜索框')
expect(!document.querySelector('#view-search'), '配置页不应显示全局搜索框')

// 搜索时忽略左侧分类，标题改为「配置搜索结果」。
configSearch.value = 'provider'
configSearch.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
const searched = text('#pane')
expect(searched.includes('配置搜索结果') && searched.includes('模型运行时'), '配置搜索未命中模型运行时')
expect(!searched.includes('指令前缀'), '配置搜索未过滤不匹配项')
const providerSelect = [...document.querySelectorAll('#pane select')]
  .find(node => [...node.options].some(option => option.value === 'codex'))
expect(providerSelect?.value === 'hermes', '模型运行时未选中当前值，实际 ' + (providerSelect?.value ?? 'null'))

// 联系人与策略：结构化联系人编辑器
configSearch.value = ''
configSearch.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
const contactsCategory = [...document.querySelectorAll('#list .user')]
  .find(node => node.textContent.includes('联系人与策略'))
contactsCategory?.click()
await new Promise(resolve => setTimeout(resolve, 50))
const contactsPane = text('#pane')
expect(contactsPane.includes('联系人列表') && contactsPane.includes('微信会话名称'), '联系人结构化编辑器未渲染')
expect(contactsPane.includes('添加联系人'), '联系人编辑器缺少添加按钮')
expect(contactsPane.includes('高级 JSON 编辑'), '联系人编辑器缺少高级 JSON 入口')

// 编辑字段产生草稿，保存后提示需重启的服务。
const prefixCategory = [...document.querySelectorAll('#list .user')]
  .find(node => node.textContent.includes('基础连接'))
prefixCategory?.click()
await new Promise(resolve => setTimeout(resolve, 50))
const prefixInput = [...document.querySelectorAll('#pane .config-field')]
  .find(node => node.textContent.includes('指令前缀'))?.querySelector('input[type=text]')
expect(prefixInput?.value === '/', '指令前缀未绑定当前值，实际 ' + (prefixInput?.value ?? 'null'))
prefixInput.value = '#'
prefixInput.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
expect(text('#c-dirty-count').includes('1 项未保存'), '修改后未显示草稿计数：' + text('#c-dirty-count'))
const saveButton = [...document.querySelectorAll('#pane .config-savebar button')]
  .find(node => node.textContent.trim() === '保存此文件')
expect(Boolean(saveButton) && !saveButton.disabled, '存在草稿时保存按钮应可用')
dom.window.confirm = () => true
saveButton?.click()
await new Promise(resolve => setTimeout(resolve, 150))
expect(text('#pane').includes('已保存'), '保存后未显示成功提示')
expect(text('#pane').includes('需重启：wxbot'), '保存后未提示需重启的服务')
expect(text('#c-dirty-count').includes('0 项未保存'), '保存后草稿未清空：' + text('#c-dirty-count'))

// 实时工作流页：每秒轮询、服务流转概览、消息详情与队列诊断入口
const workflowButton = [...document.querySelectorAll('.nav-group button')]
  .find(node => node.textContent.trim() === '实时工作流')
workflowButton?.click()
await new Promise(resolve => setTimeout(resolve, 200))

expect(document.body.classList.contains('workflow-page'), '工作流页未切换为全宽布局')
expect(!document.querySelector('#b-contacts'), '工作流页不应显示列表开关')
expect(document.querySelector('#list')?.textContent.trim() === '', '工作流页左栏应为空')
const workflowPane = text('#pane')
for (const phrase of ['实时读取 · 1 秒', '待处理轮次', '待合并收件', '等待模型', '待发送分句', '进行中异常',
  '已结束异常', '展开服务流转概览', '实时消息', '3 条已载入', '最近消息 3', '进行中 1', '异常记录 1',
  '已完成 1', 'Alice', '帮我查一下明天的天气', '产品群', '成员 小A / 小B', '已阻断',
  '处理异常，请查看详情', '清理已结束异常 (1)', '最近事件', '队列中已确认的阶段仍会显示']) {
  expect(workflowPane.includes(phrase), '工作流主区域缺少「' + phrase + '」')
}
expect(document.querySelectorAll('#pane .wf-stats > div').length === 6, '工作流统计格应为 6 个')
expect(document.querySelectorAll('#pane .wf-feed .wf-card').length === 3, '工作流消息卡片应为 3 条')

const workflowSearch = document.querySelector('#view-search')
expect(workflowSearch?.placeholder === '搜索用户 / UID / 消息 ID', '工作流搜索框占位符不符')
workflowSearch.value = '产品群'
workflowSearch.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))
expect(text('#pane').includes('产品群') && !text('#pane').includes('帮我查一下明天的天气'), '工作流搜索未过滤不匹配消息')
workflowSearch.value = ''
workflowSearch.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
await new Promise(resolve => setTimeout(resolve, 50))

// 展开服务流转概览：六个服务节点、连线标签与模型实时面板
document.querySelector('#wf-overview')?.click()
await new Promise(resolve => setTimeout(resolve, 200))
expect(document.querySelectorAll('#pane .wf-node').length === 6, '服务流转概览应有 6 个节点，实际 '
  + document.querySelectorAll('#pane .wf-node').length)
const diagramText = text('#pane .wf-canvas')
for (const phrase of ['模型执行区', '身份 · 角色 · 权限 · 调度', '收件队列', '发件队列', '微信收件与发送确认',
  '机器人收件 · 累计 3 条', '↑ 请求模型', '↓ 完整回复', '↑ 提交收件', '↑ 收到消息',
  '思考摘要', '正在整理天气', 'news_search · running', '工具 news_search · 已开始，等待确认']) {
  expect(diagramText.includes(phrase), '服务流转概览缺少「' + phrase + '」')
}

// 选中消息后显示全文、身份元数据与流转时间线
document.querySelector('[data-wf-select="b1"]')?.click()
await new Promise(resolve => setTimeout(resolve, 150))
const traceText = text('.wf-inspect')
for (const phrase of ['Alice · 流转详情', '消息正文', '回复正文', '明天有小雨，记得带伞。',
  '固定用户 ID', 'user-alice', '身份 · 已确认', '召回记忆 · 2 条', '回复决策 · 主动请求',
  '身份解析', 'Butler 请求 模型运行时', '在收发队列中查看 / 处理', '未记录的阶段保持未确认']) {
  expect(traceText.includes(phrase), '流转详情缺少「' + phrase + '」')
}
expect(document.querySelector('#wf-node-model')?.classList.contains('current'), '所选消息未标记当前服务节点')
expect(document.querySelector('#wf-edge-request')?.classList.contains('traced'), '所选消息未标记模型请求连线')
expect(document.querySelector('#wf-edge-receive')?.classList.contains('traced'), '所选消息未标记收件连线')

document.querySelector('#wf-deselect')?.click()
await new Promise(resolve => setTimeout(resolve, 50))
expect(!document.querySelector('.wf-inspect'), '取消选择后流转详情未移除')

// 异常记录筛选与动画开关
document.querySelector('[data-wf-scope="issues"]')?.click()
await new Promise(resolve => setTimeout(resolve, 50))
expect(document.querySelectorAll('#pane .wf-feed .wf-card').length === 1, '异常记录筛选应只保留 1 条消息')
expect(text('.wf-feed').includes('产品群'), '异常记录筛选未保留异常消息')
document.querySelector('[data-wf-scope="all"]')?.click()
await new Promise(resolve => setTimeout(resolve, 50))

document.querySelector('#wf-animation')?.click()
await new Promise(resolve => setTimeout(resolve, 50))
expect(text('#wf-animation').trim() === '恢复动画', '暂停动画后按钮文案未切换')
expect(document.querySelector('.wf-shell')?.classList.contains('animation-paused'), '暂停动画后未标记动画状态')
document.querySelector('#wf-animation')?.click()
await new Promise(resolve => setTimeout(resolve, 50))

// 清理已结束异常：确认后提示移除数量
dom.window.confirm = () => true
document.querySelector('#wf-clear-failed')?.click()
await new Promise(resolve => setTimeout(resolve, 200))
expect(text('#pane').includes('已移除 1 条历史记录'), '清理异常后未显示移除结果')

// 诊断入口：带当前消息筛选跳转到收发队列
document.querySelector('[data-wf-select="b1"]')?.click()
await new Promise(resolve => setTimeout(resolve, 50))
document.querySelector('#wf-diagnose')?.click()
await new Promise(resolve => setTimeout(resolve, 200))
expect(text('#pane').includes('收发队列 · Alice'), '诊断入口未切换到对应会话的队列')
expect(text('#pane').includes('按实际处理序号排列'), '诊断入口未带上待处理范围')
expect(document.querySelector('#page-tools select')?.value === 'all', '诊断入口未清除队列状态筛选')

console.warn = warn
console.error = error

if (problems.length) failures.push('控制台输出：\n  ' + problems.join('\n  '))
if (failures.length) {
  console.error('smoke failed:\n- ' + failures.join('\n- '))
  process.exit(1)
}
console.log('smoke passed：导航、实时工作流、联系人、定时任务、收发队列、配置管理、Telegram 转发页均正常渲染')
// 页面带着 1 秒倒计时定时器，断言完成后必须显式退出。
process.exit(0)
