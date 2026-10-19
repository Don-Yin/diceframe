import { describe, expect, it } from 'vitest'
import { createStepProgress } from '../src/features/create/createFlow'

describe('create progress behavior', () => {
  it('marks the first step current and the remaining steps upcoming', () => {
    expect(createStepProgress(1).map(item => item.state)).toEqual(['current', 'upcoming', 'upcoming', 'upcoming'])
  })

  it('keeps completed steps stable while the active step advances', () => {
    expect(createStepProgress(3).map(item => ({ number: item.number, state: item.state }))).toEqual([
      { number: 1, state: 'complete' },
      { number: 2, state: 'complete' },
      { number: 3, state: 'current' },
      { number: 4, state: 'upcoming' },
    ])
  })
})
