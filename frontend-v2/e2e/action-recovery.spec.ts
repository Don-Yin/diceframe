import { expect, test } from './fixtures'
import type { Page, Route } from '@playwright/test'

const ROOM_GAME = 'web|e2e-room|web_bot'

type RecoveryCode = 'ROUND_POST_COMMIT_FAILED' | 'UNKNOWN'

function gamePath(pathname: string): string {
  return decodeURIComponent(pathname.replace(/^\/api/, ''))
}

async function installRecoveryRoutes(page: Page, code: RecoveryCode) {
  let failGameRefresh = false
  let actionPosts = 0

  await page.route('**/api/games/**', async (route: Route) => {
    const request = route.request()
    const path = gamePath(new URL(request.url()).pathname)

    if (request.method() === 'POST' && path === `/games/${ROOM_GAME}/action`) {
      actionPosts += 1
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          error_code: code === 'UNKNOWN' ? 'ROUND_RESULT_UNAVAILABLE' : code,
          error: code === 'UNKNOWN'
            ? 'The action result could not be confirmed.'
            : 'The round advanced, but a follow-up step failed. Refresh to see the result.',
          phase: 'error',
        }),
      })
      return
    }

    if (request.method() === 'GET' && path === `/games/${ROOM_GAME}` && failGameRefresh) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'fixture refresh unavailable' }),
      })
      return
    }

    await route.continue()
  })

  return {
    actionPosts: () => actionPosts,
    failRefresh: () => { failGameRefresh = true },
    allowRefresh: () => { failGameRefresh = false },
  }
}

async function openRecovery(page: Page, code: RecoveryCode) {
  const routes = await installRecoveryRoutes(page, code)
  await page.goto(`/#/play?game=${encodeURIComponent(ROOM_GAME)}`)
  await expect(page.locator('.play-page')).toBeVisible()
  const composer = page.locator('.composer')
  const action = composer.locator('textarea')
  await expect(action).toBeEnabled()
  await action.fill(`recovery ${code}`)
  await composer.locator('button.primary').click()
  await expect(page.getByTestId('action-recovery')).toBeVisible()
  await expect(action).toHaveValue(`recovery ${code}`)
  expect(routes.actionPosts()).toBe(1)
  return { routes, composer, action }
}

async function openGmTaskAndFocus(page: Page) {
  const gmToggle = page.getByTestId('play-gm-toggle')
  await expect(gmToggle).toBeVisible()
  if (await gmToggle.getAttribute('aria-expanded') !== 'true') await gmToggle.click()
  const task = page.getByTestId('gm-open-action-recovery')
  await expect(task).toBeVisible()
  await task.click()
}

test('unknown action result keeps the draft locked until GET succeeds, then focuses editing', async ({ page }) => {
  const { routes, action } = await openRecovery(page, 'UNKNOWN')
  const refresh = page.getByTestId('action-recovery-refresh')

  await openGmTaskAndFocus(page)
  await expect(refresh).toBeFocused()

  routes.failRefresh()
  await refresh.click()
  await expect(page.getByTestId('action-recovery')).toBeVisible()
  await expect(action).toBeDisabled()
  await expect(action).toHaveValue('recovery UNKNOWN')
  expect(routes.actionPosts()).toBe(1)

  routes.allowRefresh()
  await refresh.click()
  await expect(page.getByTestId('action-recovery')).toContainText('刷新完成')
  await expect(page.getByTestId('action-recovery-focus')).toBeVisible()
  await expect(action).toBeEnabled()
  await expect(action).toHaveValue('recovery UNKNOWN')
  expect(routes.actionPosts()).toBe(1)

  await openGmTaskAndFocus(page)
  await expect(action).toBeFocused()
})

test('post-commit action result clears the draft only after a successful GET refresh', async ({ page }) => {
  const { routes, composer, action } = await openRecovery(page, 'ROUND_POST_COMMIT_FAILED')
  const refresh = page.getByTestId('action-recovery-refresh')

  await openGmTaskAndFocus(page)
  await expect(refresh).toBeFocused()

  routes.failRefresh()
  await refresh.click()
  await expect(page.getByTestId('action-recovery')).toBeVisible()
  await expect(action).toBeDisabled()
  expect(routes.actionPosts()).toBe(1)

  routes.allowRefresh()
  await refresh.click()
  await expect(page.getByTestId('action-recovery')).toHaveCount(0)
  await expect(action).toBeEnabled()
  await expect(action).toHaveValue('')
  const gmToggle = page.getByTestId('play-gm-toggle')
  if (await gmToggle.getAttribute('aria-expanded') !== 'true') await gmToggle.click()
  await expect(page.getByTestId('gm-open-action-recovery')).toHaveCount(0)
  expect(routes.actionPosts()).toBe(1)
  await expect(composer).toBeVisible()
})
