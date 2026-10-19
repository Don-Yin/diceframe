export function assistantSettingsCopy(locale: string) {
  return locale.startsWith('zh') ? {
    enabledHint: '关闭后隐藏悬浮的骰灵入口，不影响已保存的对话。',
    autoNavigate: '自动跳转页面', autoNavigateHint: '骰灵要带你去某个页面时直接跳转，并在对话里留下“返回上一页”。关闭后只显示前往按钮。',
    reactions: '跑团互动', reactionsHint: '对局中骰灵会对检定、战斗、剧情推进、成长和同桌变化做出表情、手势和气泡反应。',
    reactionTypes: '互动类型', reactionTypesHint: '选择骰灵要回应哪些对局事件。',
    reactionSpeech: '朗读互动', reactionSpeechHint: '用语音念出互动气泡（如“大成功！”“轮到你了！”）；轮次与掷骰提示不会朗读。',
    voiceInput: '语音输入', voiceReply: '自动朗读回复', voiceReplyHint: '每次回复完成后自动朗读；发送新消息或开始说话时停止。',
    inputServer: '使用设置中配置的语音识别（ASR）服务。',
    inputBrowser: '未配置可用的 ASR 服务，将使用浏览器自带的语音识别（Chrome / Edge）。',
    inputNone: '未配置 ASR 服务，当前浏览器也不支持语音识别。',
    outputServer: (provider: string) => `使用设置中配置的 TTS 服务（${provider}）。`,
    outputBrowser: '使用浏览器自带的语音朗读。',
    outputNone: '当前浏览器不支持语音朗读。',
  } : {
    enabledHint: 'Hide the floating familiar. Saved conversations are kept.',
    autoNavigate: 'Open pages automatically', autoNavigateHint: 'Go straight to the page the familiar opens, with "Go back" left in the conversation. When off, only a button is shown.',
    reactions: 'Table reactions', reactionsHint: 'During play the familiar reacts to checks, combat, story beats, growth and the table with faces, gestures and bubbles.',
    reactionTypes: 'Reaction types', reactionTypesHint: 'Choose which table events the familiar responds to.',
    reactionSpeech: 'Speak reactions', reactionSpeechHint: 'Read reaction bubbles aloud ("Critical success!", "Your turn!"); round and rolling beats stay silent.',
    voiceInput: 'Voice input', voiceReply: 'Read replies aloud', voiceReplyHint: 'Read each finished reply aloud; stops when you send a message or start speaking.',
    inputServer: 'Uses the speech recognition (ASR) provider configured in settings.',
    inputBrowser: 'No ASR provider is configured; the browser\'s own speech recognition is used (Chrome / Edge).',
    inputNone: 'No ASR provider is configured and this browser has no speech recognition.',
    outputServer: (provider: string) => `Uses the TTS provider configured in settings (${provider}).`,
    outputBrowser: 'Uses the browser\'s built-in speech synthesis.',
    outputNone: 'This browser cannot read text aloud.',
  }
}
