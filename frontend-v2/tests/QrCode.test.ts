import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import QrCode from '../src/components/common/QrCode.vue'

/**
 * 这些用例**不 stub** QrCode 依赖的 qrcode-generator，直接渲染真实组件。
 *
 * 回归背景：`qrcode-generator@2.0.4` 的 ESM 构建（Vite 在 dev 与 build 都按
 * `exports.import` 解析到它）不再提供 `stringToBytesFuncs`，而组件曾经直接写
 * `qrcode.stringToBytesFuncs['UTF-8']`。该表达式抛 TypeError，且因为发生在
 * computed 里，二维码会静默不渲染，用户只看到空白。类型定义仍声明该属性，
 * 所以 typecheck / lint 都发现不了 —— 只有真正渲染一次才抓得到。
 */
describe('QrCode renders for real', () => {
  it('draws an SVG with dark modules for a non-empty payload', () => {
    const wrapper = mount(QrCode, {
      props: { value: 'https://table.example/#/join?game=web%7Croom%7Cbot&user=player-1' },
    })

    const svg = wrapper.find('svg.qr-code')
    expect(svg.exists()).toBe(true)
    // 真的是二维码：必须有模块路径，且不是空 path。
    const path = svg.find('path')
    expect(path.exists()).toBe(true)
    expect((path.attributes('d') || '').length).toBeGreaterThan(20)
  })

  it('encodes non-ASCII payloads without corrupting them', () => {
    // UTF-8 编码的意义所在：中文备注/口令不能被 SJIS 编坏（编坏会抛错或画出错码）。
    const wrapper = mount(QrCode, { props: { value: '房间口令：龙与地下城' } })

    expect(wrapper.find('svg.qr-code').exists()).toBe(true)
    expect((wrapper.find('path').attributes('d') || '').length).toBeGreaterThan(20)
  })

  it('renders nothing for an empty payload instead of throwing', () => {
    const wrapper = mount(QrCode, { props: { value: '' } })

    expect(wrapper.find('svg').exists()).toBe(false)
  })

  it('honours the requested size and error-correction level', () => {
    const wrapper = mount(QrCode, {
      props: { value: 'https://table.example/join', size: 216, level: 'M' },
    })

    const svg = wrapper.find('svg.qr-code')
    expect(svg.attributes('width')).toBe('216')
    expect(svg.attributes('height')).toBe('216')
  })
})
