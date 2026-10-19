export function assistantVoiceCopy(locale: string) {
  return locale.startsWith('zh') ? {
    listen: '语音输入', stopListening: '结束语音输入', listening: '正在聆听…再点一次结束', transcribing: '正在识别…',
    speakOn: '开启语音播报', speakOff: '关闭语音播报', stopSpeaking: '停止播报',
    micDenied: '麦克风权限被拒绝，请在浏览器中允许后重试。',
    failed: '语音识别失败，请重试。',
    unsupported: '当前浏览器不支持语音输入（建议使用 Chrome / Edge，并通过 HTTPS 或 localhost 访问）。',
  } : {
    listen: 'Voice input', stopListening: 'Stop voice input', listening: 'Listening… tap again to finish', transcribing: 'Transcribing…',
    speakOn: 'Read replies aloud', speakOff: 'Stop reading replies aloud', stopSpeaking: 'Stop speaking',
    micDenied: 'Microphone access was denied. Allow it in the browser and try again.',
    failed: 'Speech recognition failed. Please try again.',
    unsupported: 'This browser does not support voice input (use Chrome or Edge over HTTPS or localhost).',
  }
}
