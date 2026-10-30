// 配置页的页面级状态：切分类、切标签页、自动刷新都不丢草稿，刷新浏览器才清空。
// data 也放在这里，切回配置页时沿用上次读取的文件版本。
import { ref } from 'vue'

export const data = ref(null)
export const error = ref('')
export const drafts = ref({})
export const messages = ref({})
export const busy = ref({})
export const section = ref('basic')
export const search = ref('')

export function draftChanges(sourceId) {
  return Object.values(drafts.value[sourceId]?.changes || {})
}

export function dirtyTotal() {
  return Object.values(drafts.value).reduce((sum, draft) => sum + Object.keys(draft.changes || {}).length, 0)
}

export function busyTotal() {
  return Object.keys(busy.value).length
}
