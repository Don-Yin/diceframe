/** Change detector, not a security signature. */
export function sourceFingerprint(source) {
  let value = 0xcbf29ce484222325n
  for (let i = 0; i < source.length; i++) {
    value = BigInt.asUintN(64, (value ^ BigInt(source.charCodeAt(i))) * 0x100000001b3n)
  }
  return value.toString(16).padStart(16, '0')
}
