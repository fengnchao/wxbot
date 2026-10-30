// 工作流页的页面级状态：切标签页再回来时保留上次快照、选中消息与概览展开状态。
// 定时器和请求控制器留在视图内，离开页面立即停止轮询。
import { reactive, ref } from 'vue'

export const data = ref(null)
export const error = ref('')
export const notice = ref('')
export const selected = ref('')
export const scope = ref('all')
export const overview = ref(false)
export const paused = ref(false)
export const expanded = reactive(new Set())
export const deleting = ref(false)
export const lastSuccess = ref(0)
export const content = ref(null)
