export function assistantConversationCopy(locale: string) {
  return locale.startsWith('zh') ? {
    history: '会话记录', newConversation: '新对话', empty: '还没有保存的会话。',
    untitled: '未命名会话', current: '当前会话', rename: '重命名', remove: '删除会话',
  } : {
    history: 'Conversations', newConversation: 'New conversation', empty: 'No saved conversations yet.',
    untitled: 'Untitled conversation', current: 'Current conversation', rename: 'Rename', remove: 'Delete conversation',
  }
}
