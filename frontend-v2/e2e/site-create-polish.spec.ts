import { expect, test } from './fixtures'
import type { Page, Route, TestInfo } from '@playwright/test'

const FIXTURE_WORLD = 'site-polish-world'
const FIXTURE_RULE = 'site-polish-rule'
const FIXTURE_GAME = 'web|site-polish|fixture'

const fixtureRule = {
  rule_id: FIXTURE_RULE,
  rule_name: 'Site Polish Rules',
  description: 'An isolated ruleset for browser layout checks.',
  attributes: [],
  skill_pool: [],
}

const fixtureRuntime = {
  id: 'core:legacy',
  version: 1,
  requested_minimum_version: 1,
  capabilities: {
    experience_profile: 'generic', character_builder: 'legacy', character_lifecycle: 'legacy',
    authoritative_intents: false, deterministic_combat: false, versioned_state: false,
    session_zero: false, tutorial_coach: false, narrative_turns: true, adventure_formats: [],
  },
}

async function fulfill(route: Route, payload: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
}

async function installIsolatedApi(page: Page) {
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = decodeURIComponent(url.pathname.replace(/^\/api/, ''))

    if (path === '/config') {
      await fulfill(route, { ai_providers: [], llm_provider_ref: '', model: '', tts_provider: 'browser', asr_provider: 'disabled' })
      return
    }
    if (path === '/world-templates') {
      await fulfill(route, { templates: [{ world_id: FIXTURE_WORLD, world_name: 'Isolated World', language: 'zh-CN', active_locale: 'zh-CN', default_rule: FIXTURE_RULE }] })
      return
    }
    if (path === '/worlds') {
      await fulfill(route, { worlds: [] })
      return
    }
    if (path === '/lorebooks') {
      await fulfill(route, { books: [] })
      return
    }
    if (path === '/character-cards') {
      await fulfill(route, { cards: [] })
      return
    }
    if (path === '/rules') {
      await fulfill(route, { rules: [{ ...fixtureRule, ruleset_runtime: fixtureRuntime }] })
      return
    }
    if (path.startsWith('/rules/')) {
      await fulfill(route, { ok: true, rule: fixtureRule, ruleset_runtime: fixtureRuntime })
      return
    }
    if (path === '/adventures') {
      await fulfill(route, { ok: true, adventures: [] })
      return
    }
    if (path === '/modules') {
      await fulfill(route, { ok: true, modules: [] })
      return
    }
    if (path === '/hub/rendezvous/config') {
      await fulfill(route, { ok: true, entry_visible: false })
      return
    }
    if (path === '/hub/preferences') {
      await fulfill(route, {
        ok: true,
        available: true,
        telemetry_enabled: false,
        choice_made: true,
        identity_created: false,
        legal_version: 'fixture-1',
        legal_accepted: true,
        legal_documents: {
          terms: { version: 'fixture-1', updated_at: '2026-01-01T00:00:00Z', language: 'zh', sha256: 'fixture-terms' },
          privacy: { version: 'fixture-1', updated_at: '2026-01-01T00:00:00Z', language: 'zh', sha256: 'fixture-privacy' },
        },
      })
      return
    }
    if (path === `/games/${FIXTURE_GAME}`) {
      await fulfill(route, {
        game_key: FIXTURE_GAME,
        run_id: 'site-polish-run',
        gm_uid: 'site-polish-gm',
        world_name: 'Isolated World',
        world_id: FIXTURE_WORLD,
        rule_id: FIXTURE_RULE,
        language: 'zh-CN',
        scene: 'Fixture scene',
        state: 'active_action',
        solo_mode: true,
        round_number: 1,
      })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/characters`)) {
      await fulfill(route, { players: [{ user_id: 'site-polish-gm', character_name: 'Fixture GM', control: { mode: 'human', revision: 1 } }] })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/log`)) {
      await fulfill(route, { log: [{ round: 1, gm_response: 'Fixture result', check_results: [{
        check_id: 'site-polish-check', actor_uid: 'site-polish-gm', actor_name: 'Fixture GM',
        label: 'Fixture check', dice: 'd20', roll: 12, rolls: [12], dc: 10, total: 12,
        verdict: 'success', is_critical: false, is_fumble: false,
      }] }], check_reveals: {}, dice_reveal_mode: 'auto' })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/private-log`)) {
      await fulfill(route, { messages: [] })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/table-talk`)) {
      await fulfill(route, { exchanges: [] })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/map`)) {
      await fulfill(route, { locations: [] })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/player-context`)) {
      await fulfill(route, { preview: false })
      return
    }
    if (path.endsWith(`/games/${FIXTURE_GAME}/health`)) {
      await fulfill(route, { events: [] })
      return
    }
    if (request.method() === 'POST' && path.endsWith(`/games/${FIXTURE_GAME}/claim-gm`)) {
      await fulfill(route, { ok: true, user_id: 'site-polish-gm' })
      return
    }

    // Keep every other application request inside this deterministic fixture.
    await fulfill(route, {})
  })
}

async function assertContained(page: Page, label: string) {
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    overflowing: Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .map(element => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 && rect.right > window.innerWidth + 1)
      .slice(0, 8)
      .map(({ element, rect }) => `${element.tagName}.${String(element.className)}:${Math.round(rect.right)}`),
  }))
  expect(geometry.overflow, `${label}: ${JSON.stringify(geometry.overflowing)}`).toBeLessThanOrEqual(1)
}

async function gotoWithStartup(page: Page, url: string, reload = false) {
  const preferences = page.waitForResponse(response => {
    const requestUrl = new URL(response.url())
    return requestUrl.pathname === '/api/hub/preferences' && response.request().method() === 'GET'
  })
  if (reload) await page.reload()
  else await page.goto(url)
  await preferences
  await expect(page.locator('.startup-privacy-modal')).toBeHidden()
}

test('isolated create wizard keeps the prefilled source path across all four steps', async ({ page }, info: TestInfo) => {
  await installIsolatedApi(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await gotoWithStartup(page, `/#/create?world=${FIXTURE_WORLD}`)
  await expect(page.locator('.create-content-stage')).toBeVisible()
  await expect(page.locator('.create-config-surface select').first()).toHaveValue(FIXTURE_WORLD)
  await expect(page.locator('.create-config-surface select').nth(1)).toHaveValue(FIXTURE_RULE)
  await expect(page.locator('.create-config-surface select').nth(2)).toHaveValue('__builtin__')
  await expect(page.locator('.create-mode-cards button').first()).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('combobox', { name: '世界模板', exact: true }).locator('option:checked')).toContainText('Isolated World')
  await expect(page.locator('.create-rule-settings')).not.toHaveAttribute('open')
  await expect(page.getByTestId('create-lorebook-summary')).not.toHaveAttribute('open')

  for (const [index, stage] of [
    ['01-world', '.create-content-stage'],
    ['02-settings', '.create-game-settings-stage'],
    ['03-characters', '.create-character-stage'],
    ['04-confirm', '.create-confirm-stage'],
  ] as const) {
    await expect(page.locator(stage)).toBeVisible()
    await assertContained(page, index)
    await page.screenshot({ path: info.outputPath(`create-${index}.png`), fullPage: true })
    if (stage !== '.create-confirm-stage') await page.locator('.create-actions .primary').click()
  }
  await expect(page.locator('.create-confirm-stage')).toContainText('Isolated World')
  await expect(page.locator('.create-confirm-stage')).toContainText('Site Polish Rules')
})

test('German, Japanese, and Russian long titles stay contained in the creation confirmation', async ({ page }, info: TestInfo) => {
  await installIsolatedApi(page)
  await page.setViewportSize({ width: 390, height: 844 })

  let firstLocale = true
  for (const locale of ['de', 'ja', 'ru'] as const) {
    await gotoWithStartup(page, '/#/create', !firstLocale)
    firstLocale = false
    await expect(page.locator('.create-content-stage')).toBeVisible()
    const advanced = page.locator('.create-launch-advanced')
    await advanced.locator('summary').click()
    const language = advanced.locator('select').first()
    await language.selectOption(locale)
    const title = `${locale}-${'Sehr lange Abenteuerbezeichnung '.repeat(5)}`
    await page.locator('.create-config-surface input').first().fill(title)
    for (let step = 1; step < 4; step += 1) await page.locator('.create-actions .primary').click()
    await expect(page.locator('.create-confirm-cover p')).toHaveText(title)
    await assertContained(page, `${locale} long title`)
    await page.screenshot({ path: info.outputPath(`create-${locale}-long-title.png`), fullPage: true })
  }
})

test('isolated dice result honors reduced motion', async ({ page }, info: TestInfo) => {
  await installIsolatedApi(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await gotoWithStartup(page, `/#/play?game=${encodeURIComponent(FIXTURE_GAME)}`)
  await expect(page.locator('.check-reveal-card').first()).toBeVisible()
  const toggle = page.getByTestId('dice-tray-toggle').first()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByTestId('dice-tray').first()).toBeHidden()
  await toggle.click()
  await expect(page.getByTestId('dice-tray').first().locator('[data-die-value]').first()).toBeVisible()
  const reducedMotionStyle = await page.locator('.check-reveal-card').first().evaluate(card => {
    card.classList.add('rolling')
    const die = card.querySelector<HTMLElement>('.check-die')
    if (!die) throw new Error('fixture check did not render a die')
    const style = getComputedStyle(die)
    const result = { animationName: style.animationName, animationDuration: style.animationDuration }
    card.classList.remove('rolling')
    return result
  })
  expect(reducedMotionStyle.animationName).toBe('none')
  await page.screenshot({ path: info.outputPath('dice-reduced-motion.png'), fullPage: true })
})
