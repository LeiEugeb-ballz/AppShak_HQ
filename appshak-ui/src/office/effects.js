export function clamp(value, min, max) {
  if (value < min) {
    return min
  }
  if (value > max) {
    return max
  }
  return value
}

export function lerp(start, end, t) {
  return start + (end - start) * t
}

export function easeInOutCubic(t) {
  const x = clamp(t, 0, 1)
  if (x < 0.5) {
    return 4 * x * x * x
  }
  return 1 - Math.pow(-2 * x + 2, 3) / 2
}

export function damp(current, target, deltaSeconds, speed = 3.2) {
  const blend = 1 - Math.exp(-Math.max(0, speed) * Math.max(0, deltaSeconds))
  return lerp(current, target, clamp(blend, 0, 1))
}

export function pulseEnvelope(progress) {
  const x = clamp(progress, 0, 1)
  return Math.sin(x * Math.PI)
}

export function queueToStress(queueSize) {
  const parsed = Number(queueSize)
  const safe = Number.isFinite(parsed) ? parsed : 0
  return clamp(safe / 20, 0, 1)
}
