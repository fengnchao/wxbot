import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matchesContact, contactStatus, pendingReasons, effectivePolicy } from '../src/contactPresentation.js'

const member = { id: 'member', kind: 'person', name: '小王', enabled: true,
  conversations: [], memberships: [{ contact: '项目群', nickname: '王工', identity_confirmed: true }] }
const inactive = { id: 'off', kind: 'person', name: '停用的人', enabled: false,
  conversations: [{ name: '旧窗口', channel_type: 'dm', enabled: false, listening: true }], memberships: [] }
test('the default conversation list contains active private chats and groups only', () => {
  const privateChat = { ...member, conversations: [{ name: '小王', channel_type: 'dm', enabled: true }] }
  const group = { id: 'group', kind: 'group', name: '项目群', enabled: true,
    conversations: [{ name: '项目群', channel_type: 'group', enabled: true }] }
  assert.equal(matchesContact(privateChat, 'chats', '', ''), true)
  assert.equal(matchesContact(group, 'chats', '', ''), true)
  assert.equal(matchesContact(member, 'chats', '', ''), false)
  assert.equal(matchesContact(inactive, 'chats', '', ''), false)
  assert.equal(matchesContact({ ...privateChat, conversations: [{ enabled: false }] }, 'chats', '', ''), false)
})
test('group-only members never appear as private contacts even when their nickname matches', () => {
  assert.equal(matchesContact(member, 'people', '', '王工'), false)
  assert.equal(matchesContact({ ...member, enabled: false }, 'people', 'disabled', ''), false)
  assert.equal(matchesContact(member, 'groups', '', ''), false)
  assert.deepEqual(pendingReasons(member), [])
  assert.equal(contactStatus(member), 'unconfigured')
})
test('a real private contact who is also a group member remains one private contact', () => {
  const row = { ...member, conversations: [{ name: '小王', channel_type: 'dm', enabled: true }] }
  assert.equal(matchesContact(row, 'people', '', '王工'), true)
  assert.equal(matchesContact(row, 'chats', '', ''), true)
})
test('group windows attached to a person do not count as private chat evidence', () => {
  const row = { ...member, conversations: [{ name: '项目群', channel_type: 'group', enabled: true }] }
  assert.equal(matchesContact(row, 'people', '', ''), false)
  assert.equal(matchesContact(row, 'chats', '', ''), false)
})
test('disabled windows are not reported as listening and filters combine', () => {
  assert.equal(contactStatus(inactive), 'disabled')
  assert.equal(matchesContact(inactive, 'people', 'listening', ''), false)
  assert.equal(matchesContact(inactive, 'people', 'disabled', '停用'), true)
  assert.equal(matchesContact(inactive, 'people', 'disabled', 'missing'), false)
})
test('a person without bindings or routes remains available as unconfigured', () => {
  const row = { ...member, enabled: false, memberships: [], bindings: [] }
  assert.equal(matchesContact(row, 'people', 'unconfigured', ''), false)
  assert.equal(matchesContact(row, 'pending', 'unconfigured', ''), true)
  assert.ok(pendingReasons(row).includes('缺少身份或窗口'))
})
test('pending identity is separate from missing private window', () => {
  const row = { ...member, memberships: [{ ...member.memberships[0], identity_confirmed: false }] }
  assert.deepEqual(pendingReasons(row), ['身份待确认'])
  assert.equal(matchesContact(row, 'pending', '', ''), true)
})
test('conversation overrides and frozen inheritance show the actual policy source', () => {
  const row = { ...member, policy: { role_skill: '派蒙', allowed_skills: ['memory'] } }
  assert.equal(effectivePolicy(row, {}).source, '联系人默认')
  assert.equal(effectivePolicy(row, { inherit_person_policy: false }).policy, null)
  const result = effectivePolicy(row, { policy: { role_skill: '助手', allowed_skills: [] } })
  assert.equal(result.source, '此窗口单独设置')
  assert.equal(result.policy.role_skill, '助手')
  assert.deepEqual(result.policy.allowed_skills, [])
})
