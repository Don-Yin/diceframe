import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { sourceFingerprint } from '../src/i18n/fingerprint.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const registry = JSON.parse(fs.readFileSync(path.join(root, '../src/localization/registry.json'), 'utf8'))
const reviewPath = path.join(root, 'src/i18n/source-review.json')

function catalog(locale) {
  const filename = path.join(root, `src/i18n/messages/${locale}.ts`)
  const tree = ts.createSourceFile(filename, fs.readFileSync(filename, 'utf8'), ts.ScriptTarget.Latest, true)
  const values = {}
  const visitObject = (object, prefix = '') => {
    for (const property of object.properties) {
      if (!ts.isPropertyAssignment(property)) throw new Error(`${locale}: catalog must use literal properties`)
      const key = prefix + property.name.text
      if (ts.isObjectLiteralExpression(property.initializer)) visitObject(property.initializer, `${key}.`)
      else if (ts.isStringLiteralLike(property.initializer)) {
        if (Object.hasOwn(values, key)) throw new Error(`${locale}: duplicate key ${key}`)
        values[key] = property.initializer.text
      } else throw new Error(`${locale}: catalog value must be literal: ${key}`)
    }
  }
  const statement = tree.statements.find(node => ts.isVariableStatement(node))
  let object = statement.declarationList.declarations[0].initializer
  if (ts.isAsExpression(object)) object = object.expression
  if (!ts.isObjectLiteralExpression(object)) throw new Error(`${locale}: missing catalog object`)
  visitObject(object)
  return values
}

const english = catalog('en')
const review = JSON.parse(fs.readFileSync(reviewPath, 'utf8'))
const args = process.argv.slice(2)
if (args[0] === 'review') {
  const locale = args[args.indexOf('--locale') + 1]
  const keyIndex = args.indexOf('--keys')
  const keys = keyIndex < 0 ? [] : args[keyIndex + 1]?.split(',').filter(Boolean) || []
  if (!args.includes('--locale') || registry[locale]?.tier !== 'community' || !keys.length) {
    throw new Error('Use review --locale de|ja|ru --keys key1,key2 after reviewing those translations')
  }
  const translated = catalog(locale)
  for (const key of keys) {
    if (!english[key] || !translated[key]) throw new Error(`Missing English or ${locale} translation: ${key}`)
  }
  for (const key of keys) review.reviews[locale][key] = sourceFingerprint(english[key])
  fs.writeFileSync(reviewPath, JSON.stringify(review, null, 2) + '\n')
  console.log(`Recorded review for ${locale}: ${keys.join(', ')}`)
} else if (!args.length || args[0] === 'check') {
  let errors = 0
  for (const [locale, policy] of Object.entries(registry)) {
    const translated = catalog(locale)
    const missing = Object.keys(english).filter(key => !Object.hasOwn(translated, key))
    const extra = Object.keys(translated).filter(key => !Object.hasOwn(english, key))
    if (policy.tier === 'core') {
      if (missing.length || extra.length || policy.status !== 'active') {
        console.error(`${locale}: core catalog mismatch; missing=${missing.join(',')} extra=${extra.join(',')}`)
        errors++
      }
      console.log(`${locale}: core, ${Object.keys(translated).length} keys`)
    } else {
      const reviewed = { ...review.baseline, ...review.reviews[locale] }
      const stale = Object.keys(english).filter(key => translated[key] && reviewed[key] !== sourceFingerprint(english[key]))
      console.log(`${locale}: community (${policy.status}), ${missing.length} missing, ${stale.length} awaiting review; English fallback`)
      if (stale.length) console.log(`  ${stale.join(', ')}`)
    }
  }
  process.exitCode = errors ? 1 : 0
} else {
  throw new Error('Expected check or review')
}
