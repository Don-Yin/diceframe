import type { CheckResult, PercentileDice } from '@/api/types'

export function validPercentileDice(dice: PercentileDice | undefined): dice is PercentileDice {
  return Boolean(dice && Number.isInteger(dice.units) && dice.units >= 0 && dice.units <= 9
    && Array.isArray(dice.tens) && Array.isArray(dice.candidates) && dice.tens.length === dice.candidates.length
    && dice.tens.length > 0 && Number.isInteger(dice.taken_index) && dice.taken_index >= 0 && dice.taken_index < dice.tens.length
    && dice.tens.every((ten, i) => Number.isInteger(ten) && ten >= 0 && ten <= 90 && ten % 10 === 0
      && (ten + dice.units || 100) === dice.candidates[i]))
}

export function projectedFaces(check: CheckResult) {
  const percentile = check.percentile_dice
  if (validPercentileDice(percentile)) {
    return [{ value: percentile.units, label: String(percentile.units), sides: 10, taken: true },
      ...percentile.tens.map((value, index) => ({ value, label: String(value).padStart(2, '0'), sides: 100, taken: index === percentile.taken_index }))]
  }
  const expression = String(check.dice || '').match(/^(\d{0,3})d(4|6|8|10|12|20|100)(?:[+-]\d+)?$/i)
  if (!expression) return []
  const sides = Number(expression[2])
  const rolls = check.rolls?.length ? check.rolls : [check.roll]
  if (rolls.some(value => typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > sides)) return []
  const adopted = rolls.findIndex(value => value === check.roll)
  return rolls.map((value, index) => ({ value: value as number, label: String(value), sides, taken: index === adopted }))
}
