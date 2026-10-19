import { computed, ref } from 'vue'
import { ApiError } from '@/api/client'
import { speechApi } from '@/api/speech'
import { useAssistantPreferences } from '@/composables/useAssistantPreferences'
import { asrLanguageFor, initializeAsr, serverAsrReady, startRecording, type RecordingSession } from '@/utils/asr'
import { initializeTts, speakingKey, stripHtml, ttsRuntimeConfig, ttsSpeak, ttsStop, ttsSupported } from '@/utils/tts'

/*
 * Voice for the global DF Agent. When the owner has configured TTS/ASR
 * providers in settings, speech goes through the owner-only assistant
 * endpoints; otherwise it falls back to the browser's own recognition and
 * synthesis. State is module-level so the launcher can mirror
 * listening/speaking while the drawer is closed.
 */

export const ASSISTANT_SPEECH_KEY = 'assistant-reply'

export type AssistantVoiceError = '' | 'mic-denied' | 'failed' | 'unsupported'
export type AssistantVoiceEngine = 'server' | 'browser' | 'none'

interface RecognitionResultLike { isFinal: boolean; 0: { transcript: string } }
interface RecognitionEventLike { resultIndex: number; results: ArrayLike<RecognitionResultLike> }
interface RecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: RecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
type RecognitionCtor = new () => RecognitionLike

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === 'undefined' || window.isSecureContext === false) return null
  const scope = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return scope.SpeechRecognition || scope.webkitSpeechRecognition || null
}

const listening = ref(false)
const transcribing = ref(false)
const interim = ref('')
const voiceError = ref<AssistantVoiceError>('')
const serverMessage = ref('')
const configLoaded = ref(false)
const speaking = computed(() => speakingKey.value === ASSISTANT_SPEECH_KEY)
const inputEngine = computed<AssistantVoiceEngine>(() => {
  void configLoaded.value
  if (serverAsrReady()) return 'server'
  return recognitionCtor() ? 'browser' : 'none'
})
const outputEngine = computed<AssistantVoiceEngine>(() => {
  void configLoaded.value
  if (ttsRuntimeConfig.value.provider !== 'browser') return 'server'
  return ttsSupported() ? 'browser' : 'none'
})
let recognition: RecognitionLike | null = null
let recording: RecordingSession | null = null
let pendingFinal: { locale: string; onFinal: (text: string) => void; generation: number } | null = null
let voiceGeneration = 0
let loadPromise: Promise<void> | null = null

export function loadAssistantVoiceConfig(force = false): Promise<void> {
  if (loadPromise && !force) return loadPromise
  loadPromise = Promise.all([initializeAsr(force), initializeTts(force)]).then(() => { configLoaded.value = true })
  return loadPromise
}

/** Markdown is rendered for reading; strip its syntax before speaking it. */
export function speakableText(markdown: string): string {
  return stripHtml(String(markdown || ''))
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[`*_~>#|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function resetError(): void {
  voiceError.value = ''
  serverMessage.value = ''
}

function startBrowserRecognition(locale: string, onFinal: (text: string) => void): void {
  const Ctor = recognitionCtor()
  if (!Ctor) { voiceError.value = 'unsupported'; return }
  const generation = ++voiceGeneration
  const session = new Ctor()
  session.lang = asrLanguageFor(locale)
  session.continuous = false
  session.interimResults = true
  session.onresult = (event) => {
    let pending = ''
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index]
      const text = result[0]?.transcript || ''
      if (generation !== voiceGeneration) return
      if (result.isFinal) { if (text.trim()) onFinal(text.trim()) } else pending += text
    }
    interim.value = pending
  }
  session.onerror = (event) => {
    if (generation !== voiceGeneration) return
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') voiceError.value = 'mic-denied'
    else if (event.error !== 'aborted' && event.error !== 'no-speech') voiceError.value = 'failed'
  }
  session.onend = () => {
    if (generation !== voiceGeneration) return
    if (recognition === session) recognition = null
    listening.value = false
    interim.value = ''
  }
  recognition = session
  listening.value = true
  try { session.start() } catch {
    if (generation === voiceGeneration) {
      recognition = null; listening.value = false; voiceError.value = 'failed'
    }
  }
}

async function startServerRecording(locale: string, onFinal: (text: string) => void): Promise<void> {
  const generation = ++voiceGeneration
  // Mark the request as active before asking for permission. This prevents
  // duplicate permission prompts and gives cancelListening() a real fence.
  listening.value = true
  pendingFinal = { locale, onFinal, generation }
  try {
    const session = await startRecording()
    if (generation !== voiceGeneration || !pendingFinal || pendingFinal.generation !== generation || !listening.value) {
      session.cancel()
      return
    }
    recording = session
  } catch (error) {
    if (generation === voiceGeneration) {
      voiceError.value = error instanceof Error && error.message === 'asr-mic-denied' ? 'mic-denied' : 'failed'
      recording = null
      pendingFinal = null
      listening.value = false
    }
    return
  }
}

async function finishServerRecording(): Promise<void> {
  const session = recording
  const target = pendingFinal
  const generation = target?.generation ?? voiceGeneration
  recording = null
  pendingFinal = null
  listening.value = false
  if (!session || !target) return
  let blob: Blob
  try {
    blob = await session.stop()
  } catch {
    if (generation !== voiceGeneration) return
    voiceError.value = 'failed'
    return
  }
  if (generation !== voiceGeneration) return
  transcribing.value = true
  try {
    const text = await speechApi.assistantTranscribe(blob, asrLanguageFor(target.locale))
    if (generation === voiceGeneration && text.trim()) target.onFinal(text.trim())
  } catch (error) {
    if (generation !== voiceGeneration) return
    if (error instanceof ApiError && error.message) serverMessage.value = error.message
    else voiceError.value = 'failed'
  } finally {
    if (generation === voiceGeneration) transcribing.value = false
  }
}

function startListening(locale: string, onFinal: (text: string) => void): void {
  if (listening.value || transcribing.value) return
  resetError()
  ttsStop()
  if (inputEngine.value === 'server') void startServerRecording(locale, onFinal)
  else startBrowserRecognition(locale, onFinal)
}

function stopListening(): void {
  if (recording) void finishServerRecording()
  else if (pendingFinal) cancelListening()
  else recognition?.stop()
}

function cancelListening(): void {
  voiceGeneration += 1
  const session = recognition
  recognition = null
  session?.abort()
  recording?.cancel()
  recording = null
  pendingFinal = null
  listening.value = false
  transcribing.value = false
  interim.value = ''
}

function speak(text: string, locale: string): void {
  const plain = speakableText(text)
  if (!plain || !ttsSupported()) return
  ttsSpeak(plain, ASSISTANT_SPEECH_KEY, { lang: asrLanguageFor(locale), assistant: true })
}

function stopSpeaking(): void {
  if (speaking.value) ttsStop()
}

export function useAssistantVoice() {
  const preferences = useAssistantPreferences()
  function setVoiceReply(value: boolean): void {
    preferences.setVoiceReply(value)
    if (!value) stopSpeaking()
  }
  return {
    listening, transcribing, interim, voiceError, serverMessage, speaking,
    inputEngine, outputEngine,
    voiceReply: preferences.voiceReply, voiceInput: preferences.voiceInput,
    startListening, stopListening, cancelListening, setVoiceReply,
    speakReply: speak, speak, stopSpeaking,
  }
}
