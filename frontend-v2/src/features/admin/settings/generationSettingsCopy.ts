export function generationSettingsCopy(locale: string) {
  return locale === 'zh-CN' ? {
    advancedTitle: '高级生成设置', advancedHint: '采样、上下文、输出预算与超时；通常保留默认值即可。',
    title: '采样与上下文', hint: '留空沿用各功能的默认采样。自定义值用于主模型与备用模型；服务商不支持时会报错，不会悄悄忽略。',
    temperature: '随机性 Temperature', top_p: '采样范围 Top P', frequency_penalty: '重复频率惩罚', presence_penalty: '重复主题惩罚',
    default: '沿用功能默认值', history: '直接携带的最近历史轮数', historyHint: '0 为自动按上下文预算选择；1–100 只携带最近这些轮次。存档全文、长期记忆和权限范围不变，仍受上下文预算限制。',
    checkTitle: '独立检定模型', checkHint: '默认跟随主模型。开启后，只有检定与世界意图规划使用所选模型，掷骰和结算仍由服务端执行。',
    checkEnabled: '使用独立检定模型', checkMissing: '请选择有效服务商和聊天模型，否则无法执行独立检定规划。',
    provider: '服务商', model: '模型', chooseProvider: '选择已保存的服务商', chooseModel: '选择聊天模型',
    save: '保存', saved: '设置已保存',
  } : {
    advancedTitle: 'Advanced generation settings', advancedHint: 'Sampling, context, output budgets and timeout. Defaults suit most games.',
    title: 'Sampling and context', hint: 'Leave blank to use each feature’s defaults. Overrides apply to the main and fallback models. Unsupported values produce an error instead of being silently ignored.',
    temperature: 'Temperature', top_p: 'Top P', frequency_penalty: 'Frequency penalty', presence_penalty: 'Presence penalty',
    default: 'Use feature default', history: 'Recent history rounds sent directly', historyHint: '0 selects automatically within the context budget; 1–100 limits direct history to recent rounds. Saved history, long-term memory and visibility stay intact; context budgets still apply.',
    checkTitle: 'Dedicated check model', checkHint: 'Follows the main model by default. When enabled, only check and world-intent planning use this model. Dice and settlement remain server-authoritative.',
    checkEnabled: 'Use a dedicated check model', checkMissing: 'Choose a valid provider and chat model before using dedicated check planning.',
    provider: 'Provider', model: 'Model', chooseProvider: 'Choose a saved provider', chooseModel: 'Choose a chat model',
    save: 'Save', saved: 'Settings saved',
  }
}
