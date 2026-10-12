import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '@/i18n'
import { createRendezvousRoom } from '@/api/peer'

describe('rendezvous room API validation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('rejects an old or incomplete Hub response before UI code maps invitations', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      room_code: 'ABCDEFGH',
      guest_token: 'old-protocol-token',
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(createRendezvousRoom(2)).rejects.toThrow(
      i18n.global.t('peerHubProtocolIncompatible'),
    )
  })

  it('accepts a complete DFP2 host-star response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      protocol_version: 2,
      topology: 'host-star',
      room_code: 'ABCDEFGH',
      host_peer_id: 'h_abcdefghijk',
      host_token: 'host-token',
      invitations: [{ peer_id: 'p_abcdefghijk', token: 'guest-token' }],
      expires_at: '2026-08-21T00:05:00+00:00',
      websocket_url: 'wss://api.example.test/v1/rendezvous/rooms/ABCDEFGH/ws',
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })))

    const room = await createRendezvousRoom(2)
    expect(room.invitations).toHaveLength(1)
  })
})
