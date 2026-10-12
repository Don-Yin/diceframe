/** Hub / 协议层的原始错误码 → 用户可读说明；未知码原样返回以便排查。 */
export function friendlyPeerDetail(
  raw: string,
  t: (key: 'peerRoomGone' | 'peerConnectionMissing' | 'peerSignalingFailed' | 'peerSignalingLost') => string,
): string {
  if (!raw) return ''
  if (raw.startsWith('signaling_lost:')) return t('peerSignalingLost')
  switch (raw) {
    case 'authentication_failed':
      return t('peerRoomGone')
    case 'peer_connection_missing':
      return t('peerConnectionMissing')
    case 'signaling_socket_failed':
    case 'signaling_socket_closed':
      return t('peerSignalingFailed')
    default:
      return raw
  }
}
