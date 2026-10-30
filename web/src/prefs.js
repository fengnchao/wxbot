// 只把展示偏好放进浏览器存储；草稿和业务数据留在内存。
const ALLOWED = ['order', 'listCollapsed', 'jobUid', 'jobShowDone', 'qScope', 'qState']

export function readPreference(name, fallback) {
  if (!ALLOWED.includes(name)) return fallback
  try {
    return JSON.parse(localStorage.getItem('butler.ui.' + name)) ?? fallback
  } catch {
    return fallback
  }
}

export function savePreference(name, value) {
  if (!ALLOWED.includes(name)) return
  try {
    localStorage.setItem('butler.ui.' + name, JSON.stringify(value))
  } catch {
    /* 显示偏好允许写入失败 */
  }
}
