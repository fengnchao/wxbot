<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiGet } from '../api'

const ctx = inject('logWebCtx', null)
const diary = ref(null)
const busy = ref(false)
const failure = ref('')
const clock = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
})
let request = 0

function currentPage() {
  const page = Number(new URL(location.href).searchParams.get('page'))
  return Number.isSafeInteger(page) && page > 0 ? page : 1
}

async function load(page = currentPage()) {
  if (busy.value) return
  const mine = ++request
  busy.value = true
  failure.value = ''
  try {
    const result = await apiGet('/api/resident/diary?page=' + page)
    if (mine !== request) return
    diary.value = result
    const url = new URL(location.href)
    if (result.page > 1) url.searchParams.set('page', result.page)
    else url.searchParams.delete('page')
    if (url.href !== location.href) history.replaceState(history.state, '', url)
    ctx?.markRefreshed?.()
  } catch (error) {
    if (mine === request) failure.value = error.message || '无法读取小潮日记。'
  } finally {
    if (mine === request) busy.value = false
  }
}

onMounted(() => load())
watch(() => ctx?.refreshKey?.value, () => load())
onUnmounted(() => { request += 1 })
</script>

<template>
  <section id="pane" class="resident-diary" aria-label="小潮日记" :aria-busy="busy">
    <div class="diary-reader">
      <p class="diary-intro">小潮空闲时的抖音观看日记。</p>

      <div v-if="failure" class="diary-state" role="alert">
        <h2>读取失败</h2>
        <p>{{ failure }}</p>
        <button type="button" @click="load()">重试</button>
      </div>
      <div v-else-if="!diary" class="diary-state" role="status">
        <p>正在读取日记…</p>
        <div class="diary-placeholder" aria-hidden="true"><span></span><span></span></div>
      </div>
      <div v-else-if="!diary.entries.length" class="diary-state" role="status">
        <h2>还没有日记</h2>
        <p>小潮记录到播放进度后，日记会出现在这里。</p>
        <button type="button" :disabled="busy" @click="load()">刷新日记</button>
      </div>
      <template v-else>
        <article v-for="entry in diary.entries" :key="entry.id" class="diary-entry">
          <div class="diary-entry-heading">
            <h2><time :datetime="entry.date">{{ entry.date }}</time></h2>
            <span>{{ clock.format(entry.updated_at * 1000) }}</span>
          </div>
          <p v-if="entry.note" class="diary-note">{{ entry.note }}</p>
          <ul v-if="entry.videos.length" class="diary-videos" aria-label="观看作品">
            <li v-for="video in entry.videos" :key="video.url">
              <a :href="video.url" target="_blank" rel="noopener noreferrer">{{ video.title }}</a>
              <span>约 {{ video.seconds }} 秒</span>
            </li>
          </ul>
        </article>

        <nav v-if="diary.pages > 1" class="diary-pager" aria-label="日记分页">
          <button type="button" :disabled="busy || diary.page <= 1" @click="load(diary.page - 1)">上一页</button>
          <span aria-live="polite">第 {{ diary.page }} 页，共 {{ diary.pages }} 页</span>
          <button type="button" :disabled="busy || diary.page >= diary.pages" @click="load(diary.page + 1)">下一页</button>
        </nav>
      </template>
    </div>
  </section>
</template>

<style src="../styles/resident-diary.css"></style>
