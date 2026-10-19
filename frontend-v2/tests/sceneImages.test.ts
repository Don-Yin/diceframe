import { describe, expect, it } from 'vitest'
import {
  MAX_SCENE_IMAGE_BYTES,
  pickSceneImageReference,
  resolveSceneImageUrl,
  sceneImageCandidates,
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
    await expect(resolveSceneImageUrl({ kind: 'builtin', id: 'ashen_throne' }))
      .resolves.toBe('/v2-assets/ui/dnd-ashen-throne.png')
    await expect(resolveSceneImageUrl({ kind: 'builtin', id: 'unknown_variant' }, 'freeform_coc'))
      .resolves.toBe('/v2-assets/ui/rules/rule-freeform-coc.webp')
    expect(sceneImageStyle('/cover"quoted.webp')).toEqual({
      '--df-bg-scene-image': 'url("/cover%22quoted.webp")',
    })
  })

  it('keeps the legacy primary cover first while normalizing optional variants', () => {
    const primary = { kind: 'builtin' as const, id: 'freeform_fantasy' }
    const variant = { kind: 'builtin' as const, id: 'freeform_fantasy_2' }
    expect(sceneImageCandidates(primary, [primary, variant, { kind: 'unknown' as never }])).toEqual([primary, variant])
  })

  it('mirrors the built-in pool when a legacy summary has no variants', () => {
    const primary = { kind: 'builtin' as const, id: 'dnd5e' }
    expect(sceneImageCandidates(primary, [])).toEqual([
      primary,
      { kind: 'builtin', id: 'ashen_throne' },
      { kind: 'builtin', id: 'moonlit_ruins' },
    ])
    expect(sceneImageCandidates(primary, [], false)).toEqual([primary])
  })

  it('keeps generated defaults within the ruleset theme', () => {
    expect(sceneImageCandidates({ kind: 'builtin', id: 'freeform_coc' }, [])
      .map(reference => reference.id)).toEqual([
        'freeform_coc', 'freeform_coc_harbor', 'freeform_coc_town',
      ])
    expect(sceneImageCandidates({ kind: 'builtin', id: 'freeform_cyberpunk' }, [])
      .map(reference => reference.id)).toEqual([
        'freeform_cyberpunk', 'freeform_cyberpunk_alley', 'freeform_cyberpunk_rooftops',
      ])
    expect(sceneImageCandidates({ kind: 'builtin', id: 'freeform_wuxia' }, [])
      .map(reference => reference.id)).toEqual([
        'freeform_wuxia', 'freeform_wuxia_mountains', 'freeform_wuxia_riverside',
      ])
  })

  it('picks one cover deterministically for a create session', () => {
    const covers = [
      { kind: 'builtin' as const, id: 'a' },
      { kind: 'builtin' as const, id: 'b' },
      { kind: 'builtin' as const, id: 'c' },
    ]
    const first = pickSceneImageReference(covers[0], covers.slice(1), 'draft-1')
    expect(first).toEqual(pickSceneImageReference(covers[0], covers.slice(1), 'draft-1'))
    expect(pickSceneImageReference(covers[0], covers.slice(1))).toEqual(covers[0])
  })
})
