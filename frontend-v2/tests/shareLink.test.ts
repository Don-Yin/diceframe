import { describe, expect, it } from 'vitest'
import { buildJoinLink, buildPairingPayload } from '../src/utils/shareLink'

describe('shareLink', () => {
  it('uses configured public base url with a reverse proxy path', () => {
    expect(buildJoinLink('web|abc|bot', 'https://example.com/trpg/')).toBe(
      'https://example.com/trpg/#/join?game=web%7Cabc%7Cbot&share=1',
    )
  })

  it('accepts a host and port without an explicit scheme', () => {
    expect(buildJoinLink('game-1', 'nas.local:18000')).toBe(
      'http://nas.local:18000/#/join?game=game-1&share=1',
    )
  })

  it('carries the backend address for standalone frontend links', () => {
    expect(buildJoinLink('game-1', 'https://play.example.com', 'tok-1', 'https://api.example.com/')).toBe(
      'https://play.example.com/#/join?game=game-1&share=1&seat=tok-1&server=https%3A%2F%2Fapi.example.com',
    )
  })

  it('puts a takeover seat token only in the hash route', () => {
    const link = new URL(buildJoinLink('game-1', 'https://play.example.com', 'tok-1'))
    expect(link.search).toBe('')
    expect(link.hash).toBe('#/join?game=game-1&share=1&seat=tok-1')
  })

  it('encodes the pairing payload with the app scheme', () => {
    expect(buildPairingPayload('192.168.1.5:18000', 'K4M9QX27')).toBe(
      'diceframe://pair?s=http%3A%2F%2F192.168.1.5%3A18000&c=K4M9QX27',
    )
  })

  it('keeps a reverse-proxy subpath in the pairing payload', () => {
    expect(buildPairingPayload('https://example.com/trpg/', 'ABCD2345')).toBe(
      'diceframe://pair?s=https%3A%2F%2Fexample.com%2Ftrpg&c=ABCD2345',
    )
  })
})
