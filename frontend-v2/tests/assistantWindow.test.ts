import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { ASSISTANT_WINDOW_MIN, useAssistantWindow } from '../src/composables/useAssistantWindow'

function host() {
  let api!: ReturnType<typeof useAssistantWindow>
  const wrapper = mount(defineComponent({ setup() { api = useAssistantWindow(); return () => null } }))
  return { api, wrapper }
}

function pointer(type: string, x: number, y: number, target: EventTarget = window) {
  const event = new PointerEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true })
  target.dispatchEvent(event)
  return event
}

describe('DF Agent floating window', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 })
  })

  it('opens beside the launcher and moves by the header within the viewport', () => {
    const { api, wrapper } = host()
    expect(api.rect.value).toEqual({ x: 836, y: 64, width: 420, height: 640 })

    const header = document.createElement('div')
    api.startMove(pointer('pointerdown', 900, 80, header))
    pointer('pointermove', -500, -500)
    pointer('pointerup', -500, -500)
    expect(api.rect.value).toMatchObject({ x: 8, y: 8 })
    expect(JSON.parse(localStorage.getItem('diceframe_assistant_window') || '{}')).toMatchObject({ x: 8, y: 8, width: 420 })
    wrapper.unmount()
  })

  it('ignores header drags that start on a control', () => {
    const { api, wrapper } = host()
    const button = document.createElement('button')
    const before = { ...api.rect.value }
    api.startMove(pointer('pointerdown', 900, 80, button))
    pointer('pointermove', 100, 100)
    pointer('pointerup', 100, 100)
    expect(api.rect.value).toEqual(before)
    wrapper.unmount()
  })

  it('resizes from edges, keeps a minimum size and switches to the wide layout', () => {
    const { api, wrapper } = host()
    api.startResize(pointer('pointerdown', 836, 400), 'w')
    pointer('pointermove', 436, 400)
    pointer('pointerup', 436, 400)
    expect(api.rect.value).toMatchObject({ x: 436, width: 820 })
    expect(api.wide.value).toBe(true)

    api.startResize(pointer('pointerdown', 436, 64), 'nw')
    pointer('pointermove', 1200, 760)
    pointer('pointerup', 1200, 760)
    expect(api.rect.value.width).toBe(ASSISTANT_WINDOW_MIN.width)
    expect(api.rect.value.height).toBe(ASSISTANT_WINDOW_MIN.height)
    expect(api.rect.value.x + api.rect.value.width).toBe(1256)
    expect(api.wide.value).toBe(false)
    wrapper.unmount()
  })

  it('restores the saved geometry and is a full-screen sheet on phones', () => {
    localStorage.setItem('diceframe_assistant_window', JSON.stringify({ x: 100, y: 120, width: 500, height: 600 }))
    const first = host()
    expect(first.api.rect.value).toEqual({ x: 100, y: 120, width: 500, height: 600 })
    first.wrapper.unmount()

    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    const phone = host()
    expect(phone.api.compact.value).toBe(true)
    expect(phone.api.style.value).toEqual({})
    phone.wrapper.unmount()
  })
})
