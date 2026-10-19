import { onUnmounted, ref } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import { speechApi } from '@/api/speech'
import { speechLocaleTag } from '@/i18n'
import { useLocale } from '@/composables/useLocale'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useToast } from '@/composables/useToast'
import { ttsRate } from '@/utils/tts'
import { asrLanguageFor, startRecording, type RecordingSession } from '@/utils/asr'

type SaveFn = () => Promise<boolean>

// 语音模型的「保存并测试」：先用调用方给的保存函数落盘，再试听 TTS 或录一段话走 ASR。
export function useSpeechModelTest() {
  const store = useSettingsStore()
  const toast = useToast()
  const { locale, t } = useLocale()

  const ttsTesting = ref(false)
  const asrTesting = ref(false)
  const asrTestRecording = ref(false)
  const asrTestText = ref('')
  let asrTestSession: RecordingSession | null = null

  async function testTts(save: SaveFn) {
    ttsTesting.value = true
    try {
      if (!await save()) return
      const blob = await speechApi.test({
        text: t('ttsTestText'),
        voice: String(store.config.tts_gm_voice || store.config.tts_default_voice || ''),
        language: speechLocaleTag(locale.value),
        speed: ttsRate(),
      })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      audio.onerror = () => URL.revokeObjectURL(url)
      await audio.play()
      toast.success(t('ttsTestStarted'))
    } catch (error: unknown) {
      toast.error(errorMessage(error))
    } finally {
      ttsTesting.value = false
    }
  }

  async function testAsr(save: SaveFn) {
    if (asrTestRecording.value) {
      await stopAsrTest()
      return
    }
    asrTesting.value = true
    asrTestText.value = ''
    try {
      if (!await save()) return
      asrTestSession = await startRecording()
      asrTestRecording.value = true
    } catch (error: unknown) {
      if (error instanceof Error && error.message === 'asr-mic-denied') toast.error(t('asrMicDenied'))
      else toast.error(t('asrRecordFailed'))
    } finally {
      asrTesting.value = false
    }
  }

  async function stopAsrTest() {
    const session = asrTestSession
    asrTestSession = null
    asrTestRecording.value = false
    if (!session) return
    asrTesting.value = true
    try {
      const blob = await session.stop()
      asrTestText.value = await speechApi.transcribeTest(blob, asrLanguageFor(locale.value))
    } catch (error: unknown) {
      toast.error(error instanceof ApiError && error.message ? error.message : t('asrFailed'))
    } finally {
      asrTesting.value = false
    }
  }

  onUnmounted(() => {
    asrTestSession?.cancel()
    asrTestSession = null
    asrTestRecording.value = false
  })

  return { ttsTesting, asrTesting, asrTestRecording, asrTestText, testTts, testAsr }
}
