import { ref } from 'vue'

// 导航顺序与分组由这一份清单决定，服务端不再提供第二个页面入口。
export const TABS = [
  { id: 'workflow', title: '实时工作流', group: '消息监控' },
  { id: 'queue', title: '收发队列', group: '消息监控' },
  { id: 'contacts', title: '联系人', group: '用户与任务' },
  { id: 'jobs', title: '定时任务', group: '用户与任务' },
  { id: 'configuration', title: '配置管理', group: '系统设置' },
  { id: 'telegram-relay', title: 'Telegram 转发', group: '系统设置' }
]

const KNOWN = new Set(TABS.map(tab => tab.id))

export function tabTitle(id) {
  const tab = TABS.find(item => item.id === id)
  return tab ? tab.title : '实时工作流'
}

// 只认 ?tab=；兼容手输的 #contacts。
function fromLocation() {
  const query = new URLSearchParams(location.search).get('tab') || ''
  if (['runtime', 'users', 'heartbeat', 'groups'].includes(query)) return 'contacts'
  if (KNOWN.has(query)) return query
  const hash = (location.hash || '').replace(/^#\/?/, '')
  return KNOWN.has(hash) ? hash : 'workflow'
}

export const activeTab = ref(fromLocation())

export function go(id) {
  const next = KNOWN.has(id) ? id : 'workflow'
  activeTab.value = next
  const target = location.pathname + '?tab=' + next
  if (location.pathname + location.search !== target) {
    history.pushState(null, '', target)
  }
}

// 前进/后退时同步，避免地址栏与页面不一致。
window.addEventListener('popstate', () => { activeTab.value = fromLocation() })
