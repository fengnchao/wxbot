// Pure presentation rules; these never infer or grant a person's identity.
export const STATUS_LABELS = {
  listening: '监听中', delivery: '仅接收推送', unconfigured: '未配置', disabled: '已停用'
}

export function contactStatus(row) {
  const windows = row.conversations || []
  const bindings = [...(row.bindings || []), ...(row.memberships || [])]
  if (!windows.length && !bindings.length) return 'unconfigured'
  if (!row.enabled || (windows.length && !windows.some(item => item.enabled))) return 'disabled'
  if (!windows.length || windows.some(item => item.enabled && item.needs_route)) return 'unconfigured'
  return windows.some(item => item.enabled && item.listening) ? 'listening' : 'delivery'
}

export function pendingReasons(row) {
  const reasons = []
  if ((row.conversations || []).some(item => item.needs_route)) reasons.push('窗口信息待补充')
  if ([...(row.bindings || []), ...(row.memberships || [])].some(item => item.identity_confirmed === false || item.identity_confirmed === 0)) reasons.push('身份待确认')
  if (row.merge_candidates?.length) reasons.push('疑似重复档案')
  if (row.memory_conflicts?.length) reasons.push('记忆冲突')
  if (row.kind === 'person' && !row.conversations?.length && !row.bindings?.length && !row.memberships?.length) {
    reasons.push('缺少身份或窗口')
  }
  return reasons
}

export function isPrivateContact(row) {
  return row.kind === 'person' && (row.conversations || []).some(item => item.channel_type === 'dm')
}

export function matchesContact(row, category, status, query, issue = '') {
  if (category === 'chats' && (!row.enabled || !(row.conversations || []).some(item =>
    item.enabled && item.channel_type === (row.kind === 'group' ? 'group' : 'dm')))) return false
  if (category === 'people' && !isPrivateContact(row)) return false
  if (category === 'groups' && row.kind !== 'group') return false
  const reasons = pendingReasons(row)
  if (category === 'pending' && (!reasons.length || (issue && !reasons.includes(issue)))) return false
  if (status && contactStatus(row) !== status) return false
  const needle = query.trim().toLocaleLowerCase()
  return !needle || JSON.stringify([row.name, row.id, row.memberships, row.conversations])
    .toLocaleLowerCase().includes(needle)
}

export function effectivePolicy(row, conversation = null) {
  if (conversation?.policy) return { policy: conversation.policy, source: '此窗口单独设置' }
  if (conversation?.inherit_person_policy === false) return { policy: null, source: '此窗口不继承默认设置' }
  if (row.policy) return { policy: row.policy, source: row.kind === 'group' ? '群聊设置' : '联系人默认' }
  return { policy: null, source: '未配置' }
}
