import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Compose component classes while allowing a caller's state class to win. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
