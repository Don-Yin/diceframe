import { createApp, h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

class FakeRecognition {
  static latest: FakeRecognition | null = null
  lang = ''
  continuous = false
  interimResults = false
  onresult = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend = null
  start = vi.fn()
  stop = vi.fn()
  abort = vi.fn()

  constructor() {
    FakeRecognition.latest = this
  }
}

vi.mock('../src/utils/asr', () => ({
  asrLanguageFor: (locale: string) => locale,
  initializeAsr: vi.fn().mockResolvedValue(undefined),
  serverAsrReady: () => false,
  startRecording: vi.fn(),
}))
vi.mock('../src/api/speech', () => ({ speechApi: { assistantTranscribe: vi.fn() } }))
vi.mock('../src/utils/tts', async () => {
  const { ref } = await import('vue')
  return {
    initializeTts: vi.fn().mockResolvedValue(undefined),
    speakingKey: ref(''),
    stripHtml: (value: string) => value,
    ttsRuntimeConfig: ref({ provider: 'browser' }),
    ttsSpeak: vi.fn(),
    ttsStop: vi.fn(),
    ttsSupported: () => true,
  }
})
vi.mock('../src/composables/useAssistantPreferences', () => ({
  useAssistantPreferences: () => ({
    voiceReply: { value: false },
    voiceInput: { value: true },
    setVoiceReply: vi.fn(),
  }),
}))

import { useAssistantVoice } from '../src/composables/useAssistantVoice'

function withSetup<T>(composable: () => T): T {
  let result!: T
  const app = createApp({ setup() { result = composable(); return () => h('div') } })
  app.mount(document.createElement('div'))
  return result
}

describe('DF Agent browser voice cancellation fences', () => {
  afterEach(() => {
    FakeRecognition.latest = null
    vi.unstubAllGlobals()
  })

  it('ignores a late browser recognition error after cancellation', () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition })
    const resolved = withSetup(() => useAssistantVoice())

    resolved.startListening('en', vi.fn())
    resolved.cancelListening()
    FakeRecognition.latest?.onerror?.({ error: 'not-allowed' })

    expect(resolved.voiceError.value).toBe('')
    expect(FakeRecognition.latest?.abort).toHaveBeenCalledOnce()
  })
})
