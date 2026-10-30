import { ref } from 'vue'

// 工作流点「在收发队列中查看 / 处理」时带上筛选条件；
// 队列页只在下次挂载时消费一次，避免影响正常进入队列页的默认筛选。
export const pendingQueueFocus = ref(null)

export function focusQueue(focus) {
  pendingQueueFocus.value = focus
}

export function takeQueueFocus() {
  const value = pendingQueueFocus.value
  pendingQueueFocus.value = null
  return value
}
