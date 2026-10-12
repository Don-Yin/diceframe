import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { installRuntimeRecovery } from './runtimeRecovery'
import './styles/tokens.css'
import './styles.css'
import './styles/v2.css'
import './styles/markdown.css'

// 视口高度兜底：部分 App 壳（如 Eagle）的工具栏显示/隐藏不会更新动态视口单位
// （100dvh 只跟浏览器原生地址栏联动），导致 fixed 元素随视口下移而对局页不跟随。
// 把真实可视区高度写入 --app-h CSS 变量，布局层用它计算高度，工具栏过渡也会触发。
function syncViewportHeight() {
  const h = window.visualViewport?.height || window.innerHeight
  document.documentElement.style.setProperty('--app-h', `${h}px`)
}
syncViewportHeight()
window.addEventListener('resize', syncViewportHeight)
window.visualViewport?.addEventListener('resize', syncViewportHeight)
window.visualViewport?.addEventListener('scroll', syncViewportHeight)

const app = createApp(App).use(createPinia()).use(router).use(i18n)

// A production rebuild replaces hashed lazy chunks. An already-open tab can
// still reference the previous names, so recover once instead of leaving a
// menu navigation apparently inert.
installRuntimeRecovery(router)

// Hash history resolves asynchronously on a direct deep link. Mounting before
// that point briefly treats /join and player /play links as owner routes and
// fires authenticated startup requests that can only return 401.
void router.isReady().then(() => app.mount('#app'))
