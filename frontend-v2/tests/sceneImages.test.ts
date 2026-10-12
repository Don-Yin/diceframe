import { describe, expect, it } from 'vitest'
import {
  MAX_SCENE_IMAGE_BYTES,
  resolveSceneImageUrl,
  sceneImageStyle,
  validateSceneImageFile,
} from '@/api/sceneImages'

describe('adventure scene images', () => {
  it('accepts supported files and rejects invalid type or size', () => {
    expect(() => validateSceneImageFile(new File(['ok'], 'cover.webp', { type: 'image/webp' }))).not.toThrow()
    expect(() => validateSceneImageFile(new File(['no'], 'cover.gif', { type: 'image/gif' })))
      .toThrow('unsupported-scene-image-type')
    const oversized = new File([new Uint8Array(MAX_SCENE_IMAGE_BYTES + 1)], 'cover.png', { type: 'image/png' })
    expect(() => validateSceneImageFile(oversized)).toThrow('scene-image-too-large')
  })

  it('resolves built-in references without an authenticated network request', async () => {
    await expect(resolveSceneImageUrl({ kind: 'builtin', id: 'freeform_coc' }))
      .resolves.toBe('/v2-assets/ui/rules/rule-freeform-coc.webp')
    expect(sceneImageStyle('/cover"quoted.webp')).toEqual({
      '--df-bg-scene-image': 'url("/cover%22quoted.webp")',
    })
  })
})
