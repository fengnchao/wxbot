import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物由 log/server.py 挂在 /app/ 下，根路径 / 重定向到 /app/。
export default defineConfig({
  base: '/app/',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets'
  },
  server: {
    // 开发时把接口转发给本机运行的 log 服务，避免跨域。
    proxy: { '/api': 'http://127.0.0.1:8788' },
    fs: { allow: ['..'] }
  }
})
