import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../src/i18n'
import MapView from '../src/features/maps/MapView.vue'
import * as client from '../src/api/client'
import * as backgrounds from '../src/api/mapBackgrounds'
import type { MapData } from '../src/api/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}

function map(name: string): MapData {
  return { active_map: { id: name, name, mode: 'graph', background: { id: `${name}-asset`, url: `blob:${name}` } }, locations: [{ id: name, name, content: `${name} detail` }] }
}

async function mountMap(apiMock: ReturnType<typeof vi.fn>) {
  vi.spyOn(client, 'api').mockImplementation(apiMock as typeof client.api)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/map', name: 'map', component: MapView }, { path: '/play', name: 'play', component: { template: '<div />' } }] })
  await router.push({ name: 'map', query: { game: 'one' } })
  await router.isReady()
  const wrapper = mount(MapView, { global: { plugins: [i18n, router] } })
  await flushPromises()
  return { wrapper, router }
}

afterEach(() => { vi.restoreAllMocks() })

describe('MapView projection lifecycle', () => {
  it('renders a successful real projection and clears it on current request failure', async () => {
    const revoke = vi.spyOn(backgrounds, 'revokeMapBackgroundAsset')
    const first = deferred<unknown>(), failed = deferred<unknown>()
    const apiMock = vi.fn((path: string) => {
      if (path === '/games') return Promise.resolve({ games: [{ game_key: 'one', world_name: 'One' }, { game_key: 'two', world_name: 'Two' }] })
      return path.includes('/one/') ? first.promise : failed.promise
    })
    const { wrapper } = await mountMap(apiMock)
    first.resolve(map('one'))
    await flushPromises()
    expect(wrapper.text()).toContain('one detail')

    await wrapper.get('select').setValue('two')
    failed.reject(new Error('offline'))
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('This game has no known places yet.')
    expect(revoke).toHaveBeenCalledWith(expect.objectContaining({ active_map: expect.objectContaining({ id: 'one' }) }))
  })

  it('keeps the newest game when map responses resolve out of order', async () => {
    const one = deferred<unknown>(), two = deferred<unknown>()
    const apiMock = vi.fn((path: string) => {
      if (path === '/games') return Promise.resolve({ games: [{ game_key: 'one' }, { game_key: 'two' }] })
      return path.includes('/one/') ? one.promise : two.promise
    })
    const { wrapper } = await mountMap(apiMock)
    await wrapper.get('select').setValue('two')
    two.resolve(map('two'))
    await flushPromises()
    one.resolve(map('one'))
    await flushPromises()
    expect(wrapper.text()).toContain('two detail')
    expect(wrapper.text()).not.toContain('one detail')
  })

  it('invalidates an in-flight response when the view unmounts', async () => {
    const pending = deferred<unknown>()
    const apiMock = vi.fn((path: string) => path === '/games'
      ? Promise.resolve({ games: [{ game_key: 'one' }] })
      : pending.promise)
    const { wrapper } = await mountMap(apiMock)
    wrapper.unmount()
    pending.resolve(map('one'))
    await flushPromises()
    expect(document.body.textContent || '').not.toContain('one detail')
  })

  it('reclaims the current background asset when the view unmounts', async () => {
    const revoke = vi.spyOn(backgrounds, 'revokeMapBackgroundAsset')
    const apiMock = vi.fn((path: string) => path === '/games'
      ? Promise.resolve({ games: [{ game_key: 'one' }] })
      : Promise.resolve(map('one')))
    const { wrapper } = await mountMap(apiMock)
    await flushPromises()
    wrapper.unmount()
    expect(revoke).toHaveBeenCalledWith(expect.objectContaining({ active_map: expect.objectContaining({ id: 'one' }) }))
  })
})
