import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const standalone = mode === 'standalone' || env.VITE_DICEFRAME_STANDALONE === 'true'
  return {
    plugins: [vue()],
    define: { __DF_STANDALONE__: JSON.stringify(standalone) },
    base: '/v2-assets/',
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    build: {
      outDir: resolve(__dirname, standalone ? 'dist' : '../static-v2'),
      emptyOutDir: true,
      // 部分手机自带/第三方浏览器内核较旧，不认识 Media Queries 4 的 range 语法
      // （如 @media (width<=800px)），会静默丢弃整个响应式块，导致手机渲染桌面布局。
      // 压低 CSS 目标，让压缩器保持传统 (max-width)/(min-width) 写法。
      cssTarget: 'chrome64',
    },
    server: { proxy: { '/api': 'http://127.0.0.1:18000' } },
  }
})
