// 接口约定：GET 只读，写操作必须带动作头。
const JSON_HEADERS = { Accept: 'application/json' }

async function parse(response) {
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) {
    throw new Error((data && data.error) || '请求失败（HTTP ' + response.status + '）')
  }
  if (data === null) throw new Error('返回内容不是 JSON')
  return data
}

export async function apiGet(url) {
  let response
  try {
    response = await fetch(url, { headers: JSON_HEADERS })
  } catch {
    throw new Error('无法连接日志服务')
  }
  return parse(response)
}

export async function apiPost(url, body, actionHeader) {
  const headers = { ...JSON_HEADERS, 'Content-Type': 'application/json' }
  if (actionHeader) headers[actionHeader] = '1'
  let response
  try {
    response = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) })
  } catch {
    throw new Error('无法连接日志服务')
  }
  return parse(response)
}

/** 秒级时间戳 → 本地时间文本；空值返回占位符。 */
export function fullTime(value) {
  if (typeof value === 'string' && value) return value
  if (!value) return '-'
  const date = new Date(value * 1000)
  const pad = n => String(n).padStart(2, '0')
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) + ' ' +
    pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds())
}

export function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value))
}
