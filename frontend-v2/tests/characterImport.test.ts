import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('@/api/client', () => ({ api: apiMock }))

import { importTavernCard } from '../src/utils/characterImport'

function cardFile(name = 'alice.json') {
  const payload = {
    spec: 'chara_card_v2',
    data: { name: 'Alice', description: 'Scout', character_book: { name: 'Alice lore', entries: [] } },
  }
  return new File([JSON.stringify(payload)], name, { type: 'application/json' })
}

function lastBody() {
  const [path, init] = apiMock.mock.calls[apiMock.mock.calls.length - 1] as [string, { method: string; body: string }]
  expect(path).toBe('/character-cards/import')
  expect(init.method).toBe('POST')
  return JSON.parse(init.body) as Record<string, unknown>
}

describe('importTavernCard include_character_book contract', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({ ok: true, card: { id: 'c1', character_name: 'Alice' } })
  })

  it('defaults to importing the embedded character lore', async () => {
    await importTavernCard(cardFile(), { target: 'character_card' })
    expect(lastBody().include_character_book).toBe(true)
  })

  it('honours an explicit opt-out in the request body', async () => {
    await importTavernCard(cardFile(), { target: 'character_card', includeCharacterBook: false })
    expect(lastBody().include_character_book).toBe(false)
  })

  it('honours an explicit opt-in and forwards the canonical target', async () => {
    await importTavernCard(cardFile(), {
      target: 'npc',
      worldId: 'w1',
      includeCharacterBook: true,
      characterUid: 'alice',
    })
    expect(lastBody()).toMatchObject({
      file_name: 'alice.json',
      target: 'npc',
      world_id: 'w1',
      include_character_book: true,
      character_uid: 'alice',
    })
  })

  it('surfaces the committed lorebook from the response', async () => {
    const lorebook = {
      book_id: 'character_card:c1',
      name: 'Alice',
      entries: 3,
      role: 'character',
      label: 'Alice',
      binding: { scope_kind: 'character', scope_id: 'alice' },
    }
    apiMock.mockResolvedValue({
      ok: true,
      card: { id: 'c1', character_name: 'Alice' },
      lorebook,
      lorebook_book_id: 'character_card:c1',
      lorebook_entries: 3,
    })

    const r = await importTavernCard(cardFile(), { target: 'character_card' })

    expect(r.lorebook?.book_id).toBe('character_card:c1')
    expect(r.lorebook?.entries).toBe(3)
    expect(r.lorebook_book_id).toBe('character_card:c1')
  })

  it('reports no lorebook when the embedded book is skipped', async () => {
    apiMock.mockResolvedValue({ ok: true, card: { id: 'c1', character_name: 'Alice' } })
    const r = await importTavernCard(cardFile(), { target: 'character_card', includeCharacterBook: false })
    expect(r.lorebook).toBeUndefined()
  })
})
