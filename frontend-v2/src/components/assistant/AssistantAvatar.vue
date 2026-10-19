<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'

/*
 * The DF Agent's face: a liquid-glass d20 familiar whose front facet is a
 * dark visor. The eyes blink, follow the pointer and change shape with the
 * mood; two floating glass hands gesture along (chin in hand while thinking,
 * shaking a die, cheering, waving…) and fidget now and then when idle.
 * Purely presentational; the owner decides the mood.
 */
export type AssistantAvatarMood =
  | 'idle' | 'happy' | 'thinking' | 'listening' | 'speaking' | 'attention' | 'surprised'
  | 'cheer' | 'nod' | 'sad' | 'dizzy'
  | 'battle' | 'hurt' | 'worried' | 'alert' | 'curious' | 'rolling'

// `hands: false` for small, inline uses where floating hands would crowd the layout.
const props = withDefaults(defineProps<{ mood?: AssistantAvatarMood; track?: boolean; hands?: boolean }>(), { mood: 'idle', track: true, hands: true })

const root = ref<HTMLElement | null>(null)
const look = ref({ x: 0, y: 0 })
const blinking = ref(false)
const gesture = ref('')
const IDLE_GESTURES = ['wave', 'stretch', 'scratch'] as const
const uid = useId()
const ids = { liquid: `df-avatar-liquid-${uid}`, hex: `df-avatar-hex-${uid}`, tri: `df-avatar-tri-${uid}`, rim: `df-avatar-rim-${uid}`, shade: `df-avatar-shade-${uid}` }
// Refracting backdrop filters render only in Chromium; elsewhere the body
// keeps the plain frosted blur instead of losing its backdrop entirely.
const liquid = typeof navigator !== 'undefined'
  && Boolean((navigator as Navigator & { userAgentData?: { brands?: { brand: string }[] } }).userAgentData?.brands?.some(item => /Chromium/i.test(item.brand)))

const HEX = 'M57.808 7.476 L83.192 22.024 Q91 26.5 91 35.5 L91 64.5 Q91 73.5 83.192 77.976 L57.808 92.524 Q50 97 42.192 92.524 L16.808 77.976 Q9 73.5 9 64.5 L9 35.5 Q9 26.5 16.808 22.024 L42.192 7.476 Q50 3 57.808 7.476Z'
const HEX_UNIT = 'M0.5781 0.0748 L0.8319 0.2202 Q0.91 0.265 0.91 0.355 L0.91 0.645 Q0.91 0.735 0.8319 0.7798 L0.5781 0.9252 Q0.5 0.97 0.4219 0.9252 L0.1681 0.7798 Q0.09 0.735 0.09 0.645 L0.09 0.355 Q0.09 0.265 0.1681 0.2202 L0.4219 0.0748 Q0.5 0.03 0.5781 0.0748Z'
const TRI_UNIT = 'M0.5716 0.1431 L0.9284 0.8569 Q1 1 0.84 1 L0.16 1 Q0 1 0.0716 0.8569 L0.4284 0.1431 Q0.5 0 0.5716 0.1431Z'
// Face-on d20: the front triangle joined to the six silhouette corners.
const FACETS = [
  [50, 22, 50, 3], [50, 22, 91, 26.5], [50, 22, 9, 26.5],
  [83, 71, 91, 26.5], [83, 71, 91, 73.5], [83, 71, 50, 97],
  [17, 71, 50, 97], [17, 71, 9, 73.5], [17, 71, 9, 26.5],
] as const

const MAX_LOOK = 3.4
const reducedMotion = typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
let frame = 0
let pointer: { x: number; y: number } | null = null
let blinkTimer: number | undefined
let glanceTimer: number | undefined
let gestureTimer: number | undefined
let lastPointerAt = 0

function applyLook() {
  frame = 0
  const element = root.value
  if (!element || !pointer) return
  const rect = element.getBoundingClientRect()
  const dx = pointer.x - (rect.left + rect.width / 2)
  const dy = pointer.y - (rect.top + rect.height / 2)
  const distance = Math.hypot(dx, dy) || 1
  const reach = Math.min(1, distance / 220)
  look.value = { x: (dx / distance) * reach * MAX_LOOK, y: (dy / distance) * reach * MAX_LOOK }
}

function onPointerMove(event: PointerEvent) {
  pointer = { x: event.clientX, y: event.clientY }
  lastPointerAt = Date.now()
  if (!frame) frame = requestAnimationFrame(applyLook)
}

function scheduleBlink() {
  blinkTimer = window.setTimeout(() => {
    blinking.value = true
    window.setTimeout(() => {
      blinking.value = false
      if (Math.random() < 0.22) window.setTimeout(() => { blinking.value = true; window.setTimeout(() => { blinking.value = false }, 110) }, 140)
    }, 120)
    scheduleBlink()
  }, 2600 + Math.random() * 3600)
}

function scheduleGlance() {
  glanceTimer = window.setTimeout(() => {
    if (Date.now() - lastPointerAt > 4000) {
      const angle = Math.random() * Math.PI * 2
      const reach = Math.random() < 0.35 ? 0 : 0.5 + Math.random() * 0.5
      look.value = { x: Math.cos(angle) * reach * MAX_LOOK, y: Math.sin(angle) * reach * MAX_LOOK * 0.7 }
    }
    scheduleGlance()
  }, 3200 + Math.random() * 3000)
}

function scheduleGesture() {
  gestureTimer = window.setTimeout(() => {
    if (props.mood === 'idle' && props.track && props.hands) {
      gesture.value = IDLE_GESTURES[Math.floor(Math.random() * IDLE_GESTURES.length)]
      window.setTimeout(() => { gesture.value = '' }, 1800)
    }
    scheduleGesture()
  }, 14000 + Math.random() * 16000)
}

onMounted(() => {
  if (reducedMotion) return
  scheduleBlink()
  scheduleGlance()
  scheduleGesture()
  if (props.track) window.addEventListener('pointermove', onPointerMove, { passive: true })
})

onBeforeUnmount(() => {
  window.clearTimeout(blinkTimer)
  window.clearTimeout(glanceTimer)
  window.clearTimeout(gestureTimer)
  if (frame) cancelAnimationFrame(frame)
  window.removeEventListener('pointermove', onPointerMove)
})
</script>

<template>
  <span
    ref="root"
    class="assistant-avatar"
    :class="[`assistant-avatar-${props.mood}`, { 'assistant-avatar-blink': blinking, 'assistant-avatar-liquid': liquid, [`assistant-avatar-gesture-${gesture}`]: gesture && props.mood === 'idle' }]"
    :style="{
      '--avatar-look-x': `${look.x}px`,
      '--avatar-look-y': `${look.y}px`,
      '--avatar-filter': `url(#${ids.liquid})`,
      '--avatar-hex': `url(#${ids.hex})`,
      '--avatar-tri': `url(#${ids.tri})`,
    }"
    aria-hidden="true"
  >
    <svg class="assistant-avatar-defs" width="0" height="0" focusable="false">
      <filter :id="ids.liquid" x="-20%" y="-20%" width="140%" height="140%" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.018 0.022" numOctaves="2" seed="7" result="noise" />
        <feGaussianBlur in="noise" stdDeviation="2.2" result="soft" />
        <feDisplacementMap in="SourceGraphic" in2="soft" scale="16" xChannelSelector="R" yChannelSelector="G" />
      </filter>
      <clipPath :id="ids.hex" clipPathUnits="objectBoundingBox"><path :d="HEX_UNIT" /></clipPath>
      <clipPath :id="ids.tri" clipPathUnits="objectBoundingBox"><path :d="TRI_UNIT" /></clipPath>
    </svg>

    <span class="assistant-avatar-spin">
      <span class="assistant-avatar-ripple" />
      <span class="assistant-avatar-ripple assistant-avatar-ripple-late" />

        <svg class="assistant-avatar-die-shadow" viewBox="0 0 100 100" focusable="false">
          <defs><filter :id="ids.shade" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" /></filter></defs>
          <path :d="HEX" :filter="`url(#${ids.shade})`" />
        </svg>
        <span class="assistant-avatar-glass" />
        <svg class="assistant-avatar-die-lines" viewBox="0 0 100 100" focusable="false">
          <defs>
            <linearGradient :id="ids.rim" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="#fff" stop-opacity="0.9" />
              <stop offset="0.38" stop-color="#fff" stop-opacity="0.1" />
              <stop offset="0.7" stop-color="#fff" stop-opacity="0.05" />
              <stop offset="1" stop-color="var(--avatar-glow)" stop-opacity="0.75" />
            </linearGradient>
          </defs>
          <g class="assistant-avatar-facets">
            <line v-for="(line, index) in FACETS" :key="index" :x1="line[0]" :y1="line[1]" :x2="line[2]" :y2="line[3]" />
          </g>
          <path class="assistant-avatar-die-rim" :d="HEX" :stroke="`url(#${ids.rim})`" />
        </svg>

      <span class="assistant-avatar-visor">
        <span class="assistant-avatar-aurora" />
        <span class="assistant-avatar-face">
          <span class="assistant-avatar-eye" />
          <span class="assistant-avatar-eye" />
        </span>
      </span>
      <span class="assistant-avatar-sheen" />
    </span>

    <template v-if="props.hands">
      <span class="assistant-avatar-hand assistant-avatar-hand-left" />
      <span class="assistant-avatar-hand assistant-avatar-hand-right"><span class="assistant-avatar-hand-die" /></span>
    </template>
    <span class="assistant-avatar-spark assistant-avatar-spark-1">✦</span>
    <span class="assistant-avatar-spark assistant-avatar-spark-2">✦</span>
    <span class="assistant-avatar-spark assistant-avatar-spark-3">✧</span>
    <span class="assistant-avatar-badge" />
  </span>
</template>

<style scoped>
.assistant-avatar {
  --avatar-glow: var(--df-interactive-strong, #89cbed);
  --avatar-warm: var(--df-accent-strong, #f0d8a0);
  --avatar-eye: #f4fbff;
  --avatar-eye-w: 8.5cqw;
  --avatar-eye-h: 19cqw;
  --avatar-eye-gap: 13cqw;
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  container-type: size;
  isolation: isolate;
}

.assistant-avatar-defs { position: absolute; width: 0; height: 0; overflow: hidden; }

.assistant-avatar-spin {
  position: absolute;
  inset: 0;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.assistant-avatar-spin > span,
.assistant-avatar-spin > svg { position: absolute; pointer-events: none; }

/* ---- Shared frosted body ---- */
.assistant-avatar-glass {
  inset: 0;
  background: radial-gradient(120% 90% at 30% 18%, rgb(255 255 255 / 0.30), rgb(255 255 255 / 0.06) 52%, rgb(255 255 255 / 0.12) 100%);
  backdrop-filter: blur(12px) saturate(185%) brightness(1.08);
  -webkit-backdrop-filter: blur(12px) saturate(185%) brightness(1.08);
}

.assistant-avatar-liquid .assistant-avatar-glass {
  backdrop-filter: var(--avatar-filter) blur(9px) saturate(190%) brightness(1.08);
}

.assistant-avatar-visor {
  overflow: hidden;
  background: radial-gradient(110% 120% at 50% 30%, rgb(22 30 44 / 0.88), rgb(6 10 18 / 0.94));
}

.assistant-avatar-aurora {
  position: absolute;
  inset: -40%;
  background: conic-gradient(from 0deg,
    color-mix(in srgb, var(--avatar-glow) 70%, transparent),
    transparent 28%,
    color-mix(in srgb, var(--avatar-warm) 55%, transparent) 50%,
    transparent 72%,
    color-mix(in srgb, var(--avatar-glow) 70%, transparent));
  filter: blur(9px);
  opacity: 0.32;
  animation: avatar-spin 14s linear infinite;
  transition: opacity 0.4s ease;
}

.assistant-avatar-face {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--avatar-eye-gap);
  transform: translate(var(--avatar-look-x), var(--avatar-look-y));
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.assistant-avatar-eye {
  position: relative;
  flex: none;
  width: var(--avatar-eye-w);
  height: var(--avatar-eye-h);
  border-radius: 999px;
  background: var(--avatar-eye);
  box-shadow: 0 0 6px color-mix(in srgb, var(--avatar-glow) 85%, transparent), 0 0 2px #fff;
  transform-origin: 50% 50%;
  transition: height 0.22s ease, width 0.22s ease, border-radius 0.22s ease, transform 0.18s ease, background-color 0.22s ease;
}

.assistant-avatar-blink .assistant-avatar-eye { transform: scaleY(0.12); }

.assistant-avatar-sheen {
  background: radial-gradient(closest-side, rgb(255 255 255 / 0.62), rgb(255 255 255 / 0));
  opacity: 0.75;
}

.assistant-avatar-ripple {
  inset: 0;
  border-radius: 50%;
  border: 1.5px solid color-mix(in srgb, var(--avatar-glow) 70%, transparent);
  opacity: 0;
}

/* ---- d20 body ---- */
.assistant-avatar-die-shadow {
  inset: 0;
  overflow: visible;
  transform: translateY(9%) scale(0.94);
  fill: rgb(0 0 0 / 0.5);
}
.assistant-avatar .assistant-avatar-glass {
  clip-path: var(--avatar-hex);
  background:
    linear-gradient(150deg, rgb(255 255 255 / 0.34), rgb(255 255 255 / 0.05) 48%, color-mix(in srgb, var(--avatar-glow) 16%, transparent) 100%);
}
.assistant-avatar-die-lines { inset: 0; overflow: visible; }
.assistant-avatar-facets line {
  stroke: rgb(255 255 255 / 0.26);
  stroke-width: 1.2;
  stroke-linecap: round;
}
.assistant-avatar-die-rim { fill: none; stroke-width: 2.2; }
.assistant-avatar .assistant-avatar-visor {
  left: 17%;
  top: 22%;
  width: 66%;
  height: 49%;
  clip-path: var(--avatar-tri);
}
.assistant-avatar .assistant-avatar-face { inset: 36% 0 2%; }
.assistant-avatar .assistant-avatar-sheen {
  top: 9%;
  left: 18%;
  width: 34%;
  height: 20%;
  border-radius: 50%;
  transform: rotate(-30deg);
  opacity: 0.6;
}
.assistant-avatar .assistant-avatar-ripple { inset: 4%; }

/* ---- Decorations ---- */
.assistant-avatar-badge {
  position: absolute;
  top: 2%;
  right: 2%;
  width: 22%;
  height: 22%;
  border-radius: 50%;
  background: var(--df-warning, #f0a33a);
  border: 2px solid rgb(10 14 22 / 0.85);
  box-shadow: 0 0 8px color-mix(in srgb, var(--df-warning, #f0a33a) 70%, transparent);
  transform: scale(0);
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  pointer-events: none;
}

.assistant-avatar-spark {
  position: absolute;
  left: 50%;
  top: 50%;
  color: var(--avatar-warm);
  font-size: 30cqw;
  line-height: 1;
  text-shadow: 0 0 6px color-mix(in srgb, var(--avatar-warm) 80%, transparent);
  opacity: 0;
  pointer-events: none;
}

/* ---- Moods ---- */
.assistant-avatar-happy .assistant-avatar-spin { transform: scale(1.06); }
.assistant-avatar-happy .assistant-avatar-eye,
.assistant-avatar-nod .assistant-avatar-eye {
  width: calc(var(--avatar-eye-w) * 2.1);
  height: calc(var(--avatar-eye-w) * 1.25);
  background: transparent;
  border: 2.2px solid var(--avatar-eye);
  border-bottom-color: transparent;
  border-radius: 50% 50% 0 0 / 100% 100% 0 0;
  box-shadow: none;
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--avatar-glow) 85%, transparent));
}
.assistant-avatar-happy .assistant-avatar-face,
.assistant-avatar-nod .assistant-avatar-face { gap: 7cqw; padding-top: 4cqw; }
.assistant-avatar-happy .assistant-avatar-face { transform: translate(calc(var(--avatar-look-x) * 0.4), calc(var(--avatar-look-y) * 0.4)); }
.assistant-avatar-happy .assistant-avatar-aurora { opacity: 0.5; }

.assistant-avatar-thinking .assistant-avatar-face { transform: translate(2.4px, -2.2px); }
.assistant-avatar-thinking .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 0.65); animation: avatar-think 1.4s ease-in-out infinite; }
.assistant-avatar-thinking .assistant-avatar-eye + .assistant-avatar-eye { animation-delay: 0.18s; }
.assistant-avatar-thinking .assistant-avatar-aurora { opacity: 0.62; animation-duration: 3.2s; }

.assistant-avatar-listening .assistant-avatar-face { transform: none; }
.assistant-avatar-listening .assistant-avatar-eye { width: calc(var(--avatar-eye-w) * 1.3); height: calc(var(--avatar-eye-h) * 0.88); }
.assistant-avatar-listening .assistant-avatar-aurora { opacity: 0.75; animation-duration: 5s; }
.assistant-avatar-listening .assistant-avatar-ripple { animation: avatar-ripple 1.8s ease-out infinite; }
.assistant-avatar-listening .assistant-avatar-ripple-late { animation-delay: 0.9s; }

.assistant-avatar-speaking .assistant-avatar-eye { animation: avatar-speak 0.9s ease-in-out infinite; }
.assistant-avatar-speaking .assistant-avatar-aurora { opacity: 0.66; animation-duration: 6s; }
.assistant-avatar-speaking .assistant-avatar-ripple { animation: avatar-ripple 2.4s ease-out infinite; }
.assistant-avatar-speaking .assistant-avatar-ripple-late { animation-delay: 1.2s; }

.assistant-avatar-attention .assistant-avatar-badge { transform: scale(1); }
.assistant-avatar-attention .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 0.86); }

.assistant-avatar-surprised .assistant-avatar-spin { transform: scale(1.08); }
.assistant-avatar-surprised .assistant-avatar-eye { width: calc(var(--avatar-eye-w) * 1.8); height: calc(var(--avatar-eye-w) * 1.8); border-radius: 50%; }

/* Critical success: star eyes, a celebratory roll and sparks. */
.assistant-avatar-cheer .assistant-avatar-spin { animation: avatar-roll 0.9s cubic-bezier(0.34, 1.4, 0.64, 1) both; }
.assistant-avatar-cheer .assistant-avatar-face { transform: none; }
.assistant-avatar-cheer .assistant-avatar-eye {
  width: calc(var(--avatar-eye-w) * 2.4);
  height: calc(var(--avatar-eye-w) * 2.4);
  border-radius: 0;
  background: var(--avatar-warm);
  clip-path: polygon(50% 0, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);
  box-shadow: none;
  filter: drop-shadow(0 0 3px var(--avatar-warm));
}
.assistant-avatar-cheer .assistant-avatar-aurora { opacity: 0.9; animation-duration: 2.4s; }
.assistant-avatar-cheer .assistant-avatar-spark { animation: avatar-spark 1.3s ease-out 0.35s both; }
.assistant-avatar-cheer .assistant-avatar-spark-1 { --spark-x: -70cqw; --spark-y: -55cqw; }
.assistant-avatar-cheer .assistant-avatar-spark-2 { --spark-x: 62cqw; --spark-y: -62cqw; animation-delay: 0.45s; }
.assistant-avatar-cheer .assistant-avatar-spark-3 { --spark-x: 8cqw; --spark-y: -88cqw; animation-delay: 0.55s; }

/* Ordinary success: a pleased little hop. */
.assistant-avatar-nod .assistant-avatar-spin { animation: avatar-hop 0.7s ease-out both; }

/* Failure: eyes droop and the avatar sinks a little. */
.assistant-avatar-sad .assistant-avatar-spin { transform: translateY(4%) scale(0.97); }
.assistant-avatar-sad .assistant-avatar-face { transform: translateY(2px); }
.assistant-avatar-sad .assistant-avatar-eye {
  width: calc(var(--avatar-eye-w) * 2.3);
  height: calc(var(--avatar-eye-w) * 0.8);
  transform: rotate(-26deg);
}
.assistant-avatar-sad .assistant-avatar-eye + .assistant-avatar-eye { transform: rotate(26deg); }
.assistant-avatar-sad .assistant-avatar-aurora { opacity: 0.14; }

/* Fumble: × eyes and a dazed wobble. */
.assistant-avatar-dizzy .assistant-avatar-spin { animation: avatar-wobble 0.9s ease-in-out 2 both; }
.assistant-avatar-dizzy .assistant-avatar-face { transform: none; }
.assistant-avatar-dizzy .assistant-avatar-eye {
  width: calc(var(--avatar-eye-w) * 2);
  height: calc(var(--avatar-eye-w) * 2);
  background: transparent;
  box-shadow: none;
}
.assistant-avatar-dizzy .assistant-avatar-eye::before,
.assistant-avatar-dizzy .assistant-avatar-eye::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 120%;
  height: 2.5px;
  border-radius: 2px;
  background: #ffb4a8;
  box-shadow: 0 0 4px rgb(255 120 100 / 0.8);
  transform: translate(-50%, -50%) rotate(45deg);
}
.assistant-avatar-dizzy .assistant-avatar-eye::after { transform: translate(-50%, -50%) rotate(-45deg); }
.assistant-avatar-dizzy .assistant-avatar-aurora { opacity: 0.2; }

/* ---- More moods ---- */
.assistant-avatar-battle .assistant-avatar-face { transform: translateY(1px); }
.assistant-avatar-battle .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 0.6); border-radius: 3px 3px 999px 999px; transform: rotate(16deg); }
.assistant-avatar-battle .assistant-avatar-eye + .assistant-avatar-eye { transform: rotate(-16deg); }
.assistant-avatar-battle .assistant-avatar-aurora { opacity: 0.7; animation-duration: 4s; }

.assistant-avatar-hurt .assistant-avatar-spin { animation: avatar-flinch 0.5s ease-out both; }
.assistant-avatar-hurt .assistant-avatar-face { transform: none; }
.assistant-avatar-hurt .assistant-avatar-eye {
  width: calc(var(--avatar-eye-w) * 1.5);
  height: calc(var(--avatar-eye-w) * 1.5);
  border-radius: 1px;
  background: transparent;
  border-top: 2.2px solid var(--avatar-eye);
  border-right: 2.2px solid var(--avatar-eye);
  box-shadow: none;
  transform: rotate(45deg);
}
.assistant-avatar-hurt .assistant-avatar-eye + .assistant-avatar-eye { transform: rotate(-135deg); }

.assistant-avatar-worried .assistant-avatar-face { animation: avatar-dart 1.1s ease-in-out infinite; }
.assistant-avatar-worried .assistant-avatar-eye { width: calc(var(--avatar-eye-w) * 1.2); height: calc(var(--avatar-eye-w) * 1.4); border-radius: 50%; }
.assistant-avatar-worried .assistant-avatar-aurora { opacity: 0.22; }

.assistant-avatar-alert .assistant-avatar-spin { animation: avatar-hop 0.6s ease-out 2 both; }
.assistant-avatar-alert .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 1.12); }
.assistant-avatar-alert .assistant-avatar-aurora { opacity: 0.7; }

.assistant-avatar-curious .assistant-avatar-spin { transform: rotate(-9deg); }
.assistant-avatar-curious .assistant-avatar-face { transform: translate(1.5px, -1px); }
.assistant-avatar-curious .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 0.7); }
.assistant-avatar-curious .assistant-avatar-eye + .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 1.05); }

.assistant-avatar-rolling .assistant-avatar-face { transform: translate(2.5px, 1.5px); }
.assistant-avatar-rolling .assistant-avatar-eye { height: calc(var(--avatar-eye-h) * 0.8); }
.assistant-avatar-rolling .assistant-avatar-spin { animation: avatar-lean 0.45s ease-in-out infinite alternate; }

/* ---- Floating hands: tucked away at rest, posed per mood ---- */
.assistant-avatar-hand {
  --hx: 0cqw;
  --hy: 0cqw;
  --hr: 0deg;
  --hs: 0.4;
  position: absolute;
  top: 58%;
  width: 25cqw;
  height: 21cqw;
  border: 1px solid rgb(255 255 255 / 0.5);
  border-radius: 52% 52% 46% 46% / 58% 58% 42% 42%;
  background:
    radial-gradient(90% 80% at 35% 28%, rgb(255 255 255 / 0.6), rgb(255 255 255 / 0.12) 62%),
    color-mix(in srgb, var(--avatar-glow) 22%, rgb(255 255 255 / 0.08));
  backdrop-filter: blur(6px) saturate(170%);
  -webkit-backdrop-filter: blur(6px) saturate(170%);
  box-shadow: inset 0 1px 1px rgb(255 255 255 / 0.7), inset -1px -2px 4px rgb(0 0 0 / 0.18), 0 3px 7px rgb(0 0 0 / 0.3);
  opacity: 0;
  pointer-events: none;
  transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs));
  transition: transform 0.38s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.22s ease;
}
/* The thumb. */
.assistant-avatar-hand::before {
  content: "";
  position: absolute;
  top: -18%;
  width: 38%;
  height: 46%;
  border: inherit;
  border-radius: 50%;
  background: inherit;
}
.assistant-avatar-hand-left { left: -14cqw; --hx: 12cqw; }
.assistant-avatar-hand-left::before { right: 8%; }
.assistant-avatar-hand-right { right: -14cqw; --hx: -12cqw; }
.assistant-avatar-hand-right::before { left: 8%; }

.assistant-avatar-hand-die {
  position: absolute;
  left: 50%;
  top: -62%;
  width: 62%;
  height: 72%;
  clip-path: polygon(50% 0, 96% 26%, 96% 74%, 50% 100%, 4% 74%, 4% 26%);
  background: linear-gradient(150deg, #fff3cf, var(--avatar-warm) 55%, #b98a3c);
  opacity: 0;
  transform: translateX(-50%) scale(0.4);
  transition: opacity 0.2s ease, transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Greeting wave (hover) and "your turn" wave. */
.assistant-avatar-happy .assistant-avatar-hand-right,
.assistant-avatar-alert .assistant-avatar-hand-right,
.assistant-avatar-gesture-wave .assistant-avatar-hand-right {
  --hx: -2cqw; --hy: -30cqw; --hr: 12deg; --hs: 1;
  opacity: 1;
  animation: avatar-wave 0.5s ease-in-out 0.15s 3 alternate;
}
.assistant-avatar-alert .assistant-avatar-hand-right { --hy: -44cqw; animation-iteration-count: 5; }

/* Hand on chin. */
.assistant-avatar-thinking .assistant-avatar-hand-right,
.assistant-avatar-curious .assistant-avatar-hand-right {
  --hx: -22cqw; --hy: -4cqw; --hr: -28deg; --hs: 0.85;
  opacity: 1;
}
.assistant-avatar-thinking .assistant-avatar-hand-right { animation: avatar-tap 1.2s ease-in-out infinite; }

/* Cupped hands by the "ears". */
.assistant-avatar-listening .assistant-avatar-hand { --hy: -22cqw; --hs: 0.9; opacity: 1; }
.assistant-avatar-listening .assistant-avatar-hand-left { --hx: 4cqw; --hr: -30deg; }
.assistant-avatar-listening .assistant-avatar-hand-right { --hx: -4cqw; --hr: 30deg; }

/* Talking with the hands. */
.assistant-avatar-speaking .assistant-avatar-hand { --hy: -4cqw; --hs: 0.8; opacity: 1; animation: avatar-gesture 0.9s ease-in-out infinite alternate; }
.assistant-avatar-speaking .assistant-avatar-hand-left { --hx: 6cqw; --hr: -14deg; }
.assistant-avatar-speaking .assistant-avatar-hand-right { --hx: -6cqw; --hr: 14deg; animation-delay: 0.45s; }

/* Both hands up. */
.assistant-avatar-cheer .assistant-avatar-hand,
.assistant-avatar-gesture-stretch .assistant-avatar-hand { --hy: -50cqw; --hs: 1; opacity: 1; animation: avatar-wave 0.32s ease-in-out 0.2s 6 alternate; }
.assistant-avatar-cheer .assistant-avatar-hand-left,
.assistant-avatar-gesture-stretch .assistant-avatar-hand-left { --hx: 0cqw; --hr: -22deg; }
.assistant-avatar-cheer .assistant-avatar-hand-right,
.assistant-avatar-gesture-stretch .assistant-avatar-hand-right { --hx: 0cqw; --hr: 22deg; }
.assistant-avatar-gesture-stretch .assistant-avatar-hand { animation: avatar-stretch 1.6s ease-in-out both; }

/* Fist pump. */
.assistant-avatar-nod .assistant-avatar-hand-right { --hx: -2cqw; --hy: -26cqw; --hr: -8deg; --hs: 0.95; opacity: 1; animation: avatar-pump 0.4s ease-out 0.1s 2 alternate; }

.assistant-avatar-sad .assistant-avatar-hand { --hy: 14cqw; --hs: 0.8; opacity: 0.85; }
.assistant-avatar-sad .assistant-avatar-hand-left { --hx: 8cqw; --hr: 32deg; }
.assistant-avatar-sad .assistant-avatar-hand-right { --hx: -8cqw; --hr: -32deg; }

.assistant-avatar-dizzy .assistant-avatar-hand { --hy: -18cqw; --hs: 0.85; opacity: 1; animation: avatar-flail 0.28s ease-in-out infinite alternate; }
.assistant-avatar-dizzy .assistant-avatar-hand-left { --hx: -2cqw; --hr: -40deg; }
.assistant-avatar-dizzy .assistant-avatar-hand-right { --hx: 2cqw; --hr: 40deg; animation-delay: 0.14s; }

/* Guard up. */
.assistant-avatar-battle .assistant-avatar-hand { --hy: 8cqw; --hs: 0.82; opacity: 1; animation: avatar-jab 0.5s ease-in-out infinite alternate; }
.assistant-avatar-battle .assistant-avatar-hand-left { --hx: 14cqw; --hr: 10deg; }
.assistant-avatar-battle .assistant-avatar-hand-right { --hx: -14cqw; --hr: -10deg; animation-delay: 0.25s; }

/* Covering up. */
.assistant-avatar-hurt .assistant-avatar-hand { --hy: -12cqw; --hs: 0.8; opacity: 1; }
.assistant-avatar-hurt .assistant-avatar-hand-left { --hx: 24cqw; --hr: 24deg; }
.assistant-avatar-hurt .assistant-avatar-hand-right { --hx: -24cqw; --hr: -24deg; }

/* Wringing hands. */
.assistant-avatar-worried .assistant-avatar-hand { --hy: 6cqw; --hs: 0.72; opacity: 1; animation: avatar-fidget 0.6s ease-in-out infinite alternate; }
.assistant-avatar-worried .assistant-avatar-hand-left { --hx: 30cqw; }
.assistant-avatar-worried .assistant-avatar-hand-right { --hx: -30cqw; animation-delay: 0.3s; }

/* Hands thrown open. */
.assistant-avatar-surprised .assistant-avatar-hand { --hy: -30cqw; --hs: 0.9; opacity: 1; }
.assistant-avatar-surprised .assistant-avatar-hand-left { --hx: -4cqw; --hr: -42deg; }
.assistant-avatar-surprised .assistant-avatar-hand-right { --hx: 4cqw; --hr: 42deg; }

/* Raising a hand for attention. */
.assistant-avatar-attention .assistant-avatar-hand-right { --hx: -4cqw; --hy: -36cqw; --hr: 0deg; --hs: 0.85; opacity: 1; }

/* Shaking a die, the other hand ready to catch. */
.assistant-avatar-rolling .assistant-avatar-hand-right { --hx: -4cqw; --hy: -12cqw; --hr: 0deg; --hs: 1; opacity: 1; animation: avatar-shake 0.12s linear infinite alternate; }
.assistant-avatar-rolling .assistant-avatar-hand-left { --hx: 4cqw; --hy: 2cqw; --hr: 20deg; --hs: 0.8; opacity: 1; }
.assistant-avatar-rolling .assistant-avatar-hand-die { opacity: 1; transform: translateX(-50%) scale(1); animation: avatar-spin 0.5s linear infinite; }

/* Idle moment: scratching the top of the head. */
.assistant-avatar-gesture-scratch .assistant-avatar-hand-left { --hx: 14cqw; --hy: -52cqw; --hr: -60deg; --hs: 0.8; opacity: 1; animation: avatar-tap 0.35s ease-in-out 4; }

@keyframes avatar-wave { from { transform: translate(var(--hx), var(--hy)) rotate(calc(var(--hr) - 18deg)) scale(var(--hs)); } to { transform: translate(var(--hx), var(--hy)) rotate(calc(var(--hr) + 18deg)) scale(var(--hs)); } }
@keyframes avatar-tap { 0%, 100% { transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs)); } 50% { transform: translate(var(--hx), calc(var(--hy) - 3cqw)) rotate(calc(var(--hr) + 8deg)) scale(var(--hs)); } }
@keyframes avatar-gesture { from { transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs)); } to { transform: translate(var(--hx), calc(var(--hy) - 10cqw)) rotate(calc(var(--hr) * -1)) scale(var(--hs)); } }
@keyframes avatar-pump { from { transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs)); } to { transform: translate(var(--hx), calc(var(--hy) - 12cqw)) rotate(var(--hr)) scale(var(--hs)); } }
@keyframes avatar-flail { from { transform: translate(var(--hx), var(--hy)) rotate(calc(var(--hr) - 25deg)) scale(var(--hs)); } to { transform: translate(var(--hx), calc(var(--hy) + 6cqw)) rotate(calc(var(--hr) + 25deg)) scale(var(--hs)); } }
@keyframes avatar-jab { from { transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs)); } to { transform: translate(var(--hx), calc(var(--hy) - 4cqw)) rotate(var(--hr)) scale(calc(var(--hs) * 1.15)); } }
@keyframes avatar-fidget { from { transform: translate(var(--hx), var(--hy)) rotate(-10deg) scale(var(--hs)); } to { transform: translate(var(--hx), calc(var(--hy) - 2cqw)) rotate(10deg) scale(var(--hs)); } }
@keyframes avatar-shake { from { transform: translate(calc(var(--hx) - 2cqw), var(--hy)) rotate(-12deg) scale(var(--hs)); } to { transform: translate(calc(var(--hx) + 2cqw), calc(var(--hy) - 3cqw)) rotate(12deg) scale(var(--hs)); } }
@keyframes avatar-stretch { 0% { transform: translate(var(--hx), 0) rotate(0) scale(0.5); } 45%, 70% { transform: translate(var(--hx), var(--hy)) rotate(var(--hr)) scale(var(--hs)); } 100% { transform: translate(var(--hx), 0) rotate(0) scale(0.5); opacity: 0; } }
@keyframes avatar-flinch { 0% { transform: translateX(0); } 25% { transform: translateX(-9%) rotate(-6deg) scale(0.94); } 60% { transform: translateX(5%) rotate(3deg); } 100% { transform: none; } }
@keyframes avatar-dart { 0%, 100% { transform: translate(-2px, 1px); } 50% { transform: translate(2px, 1px); } }
@keyframes avatar-lean { from { transform: rotate(-4deg); } to { transform: rotate(5deg) translateY(-3%); } }

@keyframes avatar-spin { to { transform: rotate(1turn); } }
@keyframes avatar-think { 0%, 100% { transform: translateX(-1.5px); } 50% { transform: translateX(1.5px); } }
@keyframes avatar-speak { 0%, 100% { transform: scaleY(1); } 45% { transform: scaleY(0.62) translateY(1px); } }
@keyframes avatar-ripple { 0% { opacity: 0.75; transform: scale(1); } 100% { opacity: 0; transform: scale(1.55); } }
@keyframes avatar-roll {
  0% { transform: translateY(0) rotate(0) scale(1); }
  35% { transform: translateY(-22%) rotate(200deg) scale(1.1); }
  70% { transform: translateY(0) rotate(360deg) scale(1.12); }
  100% { transform: translateY(0) rotate(360deg) scale(1.08); }
}
@keyframes avatar-hop { 0%, 100% { transform: translateY(0); } 40% { transform: translateY(-12%); } 70% { transform: translateY(2%); } }
@keyframes avatar-wobble {
  0%, 100% { transform: rotate(0); }
  20% { transform: rotate(-14deg) translateX(-4%); }
  45% { transform: rotate(10deg) translateX(3%); }
  70% { transform: rotate(-6deg); }
}
@keyframes avatar-spark {
  0% { opacity: 0; transform: translate(-50%, -50%) scale(0.3); }
  25% { opacity: 1; }
  100% { opacity: 0; transform: translate(calc(-50% + var(--spark-x)), calc(-50% + var(--spark-y))) scale(1) rotate(90deg); }
}

@media (prefers-reduced-motion: reduce) {
  .assistant-avatar-spin, .assistant-avatar-face, .assistant-avatar-eye { transition: none; }
  .assistant-avatar-aurora, .assistant-avatar-eye, .assistant-avatar-ripple, .assistant-avatar-spin, .assistant-avatar-spark,
  .assistant-avatar-face, .assistant-avatar-hand, .assistant-avatar-hand-die { animation: none !important; }
  .assistant-avatar-hand { transition: opacity 0.2s ease; }
}
</style>
