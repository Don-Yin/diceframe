import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ImageLightbox from '../src/components/common/ImageLightbox.vue'
import SceneImageBlock from '../src/components/play/SceneImageBlock.vue'

vi.mock('../src/api/generatedImages', () => ({
  generatedImageUrl: vi.fn(async () => 'blob:scene-image'),
}))

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('generated scene images', () => {
  it('opens the full-size lightbox when the image is clicked', async () => {
    const wrapper = mount(SceneImageBlock, {
      props: { assetId: 'asset-1', gameKey: 'web:room:game' },
    })
    await flushPromises()

    await wrapper.get('img').trigger('click')
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    expect(document.body.querySelector('.image-lightbox img')?.getAttribute('src')).toBe('blob:scene-image')

    await wrapper.getComponent(ImageLightbox).vm.$emit('close')
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })
})
