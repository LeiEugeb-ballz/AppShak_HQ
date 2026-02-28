import { clamp, lerp } from './effects'

export const OFFICE_ZONES = {
  supervisorDesk: { x: 0.78, y: 0.2, label: 'Supervisor Control' },
  commandDesk: { x: 0.18, y: 0.49, label: 'Command Desk' },
  reconDesk: { x: 0.2, y: 0.8, label: 'Recon Desk' },
  forgeDesk: { x: 0.78, y: 0.8, label: 'Forge Desk' },
  boardroom: { x: 0.5, y: 0.52, label: 'Boardroom' },
  dispatchZone: { x: 0.34, y: 0.42, label: 'Dispatch Zone' },
  waterCooler: { x: 0.92, y: 0.1, label: 'Water Cooler' },
  securityCheckpoint: { x: 0.06, y: 0.32, label: 'Security Checkpoint' },
  supervisorIdle: { x: 0.58, y: 0.3, label: 'Supervisor Idle' },
}

const DESK_DEFINITIONS = [
  { zone: 'supervisorDesk', monitorColor: '#6aa3ff' },
  { zone: 'commandDesk', monitorColor: '#6ea9d8' },
  { zone: 'reconDesk', monitorColor: '#67c9ff' },
  { zone: 'forgeDesk', monitorColor: '#f4b470' },
]

const AVATAR_COLORS = {
  supervisor: '#7db8ff',
  recon: '#7de0ff',
  forge: '#f8c18f',
  command: '#b7c3de',
}

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function rgbaFromHex(hex, alpha) {
  const clean = String(hex).replace('#', '')
  if (clean.length !== 6) {
    return `rgba(255, 255, 255, ${clamp(alpha, 0, 1)})`
  }
  const r = Number.parseInt(clean.slice(0, 2), 16)
  const g = Number.parseInt(clean.slice(2, 4), 16)
  const b = Number.parseInt(clean.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${clamp(alpha, 0, 1)})`
}

function drawRoundedRect(ctx, x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, width * 0.5, height * 0.5))
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + width - r, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + r)
  ctx.lineTo(x + width, y + height - r)
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
  ctx.lineTo(x + r, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

function roomGeometry(width, height) {
  return {
    top: height * 0.11,
    bottom: height * 0.94,
    leftTop: width * 0.15,
    rightTop: width * 0.85,
    leftBottom: width * 0.03,
    rightBottom: width * 0.97,
  }
}

function rowBounds(geometry, yNorm) {
  const y = clamp(yNorm, 0, 1)
  return {
    y: lerp(geometry.top, geometry.bottom, y),
    left: lerp(geometry.leftTop, geometry.leftBottom, y),
    right: lerp(geometry.rightTop, geometry.rightBottom, y),
  }
}

function projectPoint(geometry, xNorm, yNorm) {
  const row = rowBounds(geometry, yNorm)
  const x = lerp(row.left, row.right, clamp(xNorm, 0, 1))
  return {
    x,
    y: row.y,
    scale: lerp(0.68, 1.14, clamp(yNorm, 0, 1)),
  }
}

function drawBackdrop(ctx, width, height, lightLevel, stressLevel) {
  const wallGradient = ctx.createLinearGradient(0, 0, 0, height)
  wallGradient.addColorStop(0, rgbaFromHex('#0a121a', 1))
  wallGradient.addColorStop(1, rgbaFromHex('#070c12', 1))
  ctx.fillStyle = wallGradient
  ctx.fillRect(0, 0, width, height)

  const glow = ctx.createRadialGradient(width * 0.6, height * 0.15, 0, width * 0.6, height * 0.25, width * 0.8)
  const glowStrength = clamp(0.16 + lightLevel * 0.23, 0.1, 0.45)
  glow.addColorStop(0, rgbaFromHex('#8bb5ff', glowStrength))
  glow.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, width, height)

  if (stressLevel > 0.02) {
    const stressOverlay = ctx.createLinearGradient(0, 0, width, height)
    stressOverlay.addColorStop(0, rgbaFromHex('#7a2025', 0.02 + stressLevel * 0.08))
    stressOverlay.addColorStop(1, rgbaFromHex('#8f232d', 0.05 + stressLevel * 0.16))
    ctx.fillStyle = stressOverlay
    ctx.fillRect(0, 0, width, height)
  }
}

function drawRoomShell(ctx, geometry, lightLevel) {
  const topLeft = rowBounds(geometry, 0)
  const bottomLeft = rowBounds(geometry, 1)

  ctx.beginPath()
  ctx.moveTo(topLeft.left, topLeft.y)
  ctx.lineTo(topLeft.right, topLeft.y)
  ctx.lineTo(bottomLeft.right, bottomLeft.y)
  ctx.lineTo(bottomLeft.left, bottomLeft.y)
  ctx.closePath()

  const floorGradient = ctx.createLinearGradient(0, geometry.top, 0, geometry.bottom)
  floorGradient.addColorStop(0, rgbaFromHex('#182432', 0.9))
  floorGradient.addColorStop(1, rgbaFromHex('#0f1823', 0.98))
  ctx.fillStyle = floorGradient
  ctx.fill()

  ctx.lineWidth = 2
  ctx.strokeStyle = rgbaFromHex('#5e738f', 0.22 + lightLevel * 0.22)
  ctx.stroke()
}

function drawFloorGrid(ctx, geometry, lightLevel) {
  ctx.lineWidth = 1
  const gridColor = rgbaFromHex('#85a2c6', 0.06 + lightLevel * 0.14)
  ctx.strokeStyle = gridColor

  for (let row = 1; row <= 12; row += 1) {
    const line = rowBounds(geometry, row / 12)
    ctx.beginPath()
    ctx.moveTo(line.left, line.y)
    ctx.lineTo(line.right, line.y)
    ctx.stroke()
  }

  for (let col = 0; col <= 14; col += 1) {
    const xRatio = col / 14
    ctx.beginPath()
    for (let row = 0; row <= 16; row += 1) {
      const point = projectPoint(geometry, xRatio, row / 16)
      if (row === 0) {
        ctx.moveTo(point.x, point.y)
      } else {
        ctx.lineTo(point.x, point.y)
      }
    }
    ctx.stroke()
  }
}

function drawDesk(ctx, geometry, width, height, zoneName, monitorColor, lightLevel) {
  const zone = OFFICE_ZONES[zoneName]
  if (!zone) {
    return
  }
  const point = projectPoint(geometry, zone.x, zone.y)
  const deskWidth = Math.max(52, width * 0.085 * point.scale)
  const deskHeight = Math.max(20, height * 0.03 * point.scale)
  const x = point.x - deskWidth * 0.5
  const y = point.y - deskHeight * 0.5

  drawRoundedRect(ctx, x, y, deskWidth, deskHeight, deskHeight * 0.32)
  ctx.fillStyle = rgbaFromHex('#2a3a4d', 0.95)
  ctx.fill()
  ctx.strokeStyle = rgbaFromHex('#6782a3', 0.35 + lightLevel * 0.25)
  ctx.lineWidth = 1.2
  ctx.stroke()

  const monitorWidth = deskWidth * 0.22
  const monitorHeight = deskHeight * 0.56
  const monitorX = point.x - monitorWidth * 0.5
  const monitorY = y - monitorHeight * 0.7
  drawRoundedRect(ctx, monitorX, monitorY, monitorWidth, monitorHeight, monitorHeight * 0.2)
  ctx.fillStyle = rgbaFromHex(monitorColor, 0.24 + lightLevel * 0.42)
  ctx.fill()
}

function drawBoardroomTable(ctx, geometry, width, height, lightLevel) {
  const zone = OFFICE_ZONES.boardroom
  const point = projectPoint(geometry, zone.x, zone.y)
  const radiusX = Math.max(45, width * 0.12 * point.scale)
  const radiusY = Math.max(18, height * 0.038 * point.scale)
  ctx.beginPath()
  ctx.ellipse(point.x, point.y, radiusX, radiusY, 0, 0, Math.PI * 2)
  ctx.fillStyle = rgbaFromHex('#3c4c60', 0.96)
  ctx.fill()
  ctx.strokeStyle = rgbaFromHex('#7d95b4', 0.3 + lightLevel * 0.24)
  ctx.lineWidth = 1.5
  ctx.stroke()
}

function drawWaterCooler(ctx, geometry, width, height) {
  const zone = OFFICE_ZONES.waterCooler
  const point = projectPoint(geometry, zone.x, zone.y)
  const bodyWidth = Math.max(14, width * 0.019 * point.scale)
  const bodyHeight = Math.max(26, height * 0.064 * point.scale)
  const bodyX = point.x - bodyWidth * 0.5
  const bodyY = point.y - bodyHeight

  drawRoundedRect(ctx, bodyX, bodyY, bodyWidth, bodyHeight, bodyWidth * 0.25)
  ctx.fillStyle = rgbaFromHex('#d8e7fa', 0.22)
  ctx.fill()
  ctx.strokeStyle = rgbaFromHex('#a8c0e5', 0.38)
  ctx.lineWidth = 1
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(point.x, bodyY - bodyWidth * 0.2, bodyWidth * 0.44, 0, Math.PI * 2)
  ctx.fillStyle = rgbaFromHex('#78baff', 0.26)
  ctx.fill()
}

function drawSecurityCheckpoint(ctx, geometry, width, height, pulseIntensity, pulseColor) {
  const zone = OFFICE_ZONES.securityCheckpoint
  const point = projectPoint(geometry, zone.x, zone.y)
  const panelWidth = Math.max(16, width * 0.018 * point.scale)
  const panelHeight = Math.max(62, height * 0.12 * point.scale)
  const x = point.x - panelWidth * 0.5
  const y = point.y - panelHeight * 0.5

  drawRoundedRect(ctx, x, y, panelWidth, panelHeight, panelWidth * 0.3)
  ctx.fillStyle = rgbaFromHex('#2f455d', 0.88)
  ctx.fill()
  ctx.strokeStyle = rgbaFromHex('#7f9ec0', 0.32)
  ctx.lineWidth = 1.1
  ctx.stroke()

  const ledRadius = Math.max(5, panelWidth * 0.35)
  const ledY = y + panelHeight * 0.26
  ctx.beginPath()
  ctx.arc(point.x, ledY, ledRadius, 0, Math.PI * 2)
  ctx.fillStyle = rgbaFromHex('#5f87bd', 0.35)
  ctx.fill()

  if (pulseIntensity > 0.01) {
    const gradient = ctx.createRadialGradient(point.x, ledY, ledRadius * 0.1, point.x, ledY, ledRadius * 3.8)
    gradient.addColorStop(0, rgbaFromHex(pulseColor, 0.35 * pulseIntensity))
    gradient.addColorStop(1, rgbaFromHex(pulseColor, 0))
    ctx.fillStyle = gradient
    ctx.beginPath()
    ctx.arc(point.x, ledY, ledRadius * 3.8, 0, Math.PI * 2)
    ctx.fill()
  }
}

function drawZonePulses(ctx, geometry, pulseList) {
  if (!Array.isArray(pulseList)) {
    return
  }
  for (const pulse of pulseList) {
    if (!isRecord(pulse) || typeof pulse.zone !== 'string') {
      continue
    }
    const zone = OFFICE_ZONES[pulse.zone]
    if (!zone) {
      continue
    }
    const intensity = clamp(Number(pulse.intensity), 0, 1)
    if (intensity < 0.01) {
      continue
    }
    const point = projectPoint(geometry, zone.x, zone.y)
    const radius = 32 * point.scale + 56 * intensity
    const color = typeof pulse.color === 'string' ? pulse.color : '#6ca8ff'
    const gradient = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius)
    gradient.addColorStop(0, rgbaFromHex(color, 0.36 * intensity))
    gradient.addColorStop(1, rgbaFromHex(color, 0))
    ctx.fillStyle = gradient
    ctx.beginPath()
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2)
    ctx.fill()
  }
}

function drawAvatars(ctx, geometry, avatars) {
  if (!isRecord(avatars)) {
    return
  }
  for (const [avatarId, position] of Object.entries(avatars)) {
    if (!isRecord(position)) {
      continue
    }
    const xNorm = Number(position.x)
    const yNorm = Number(position.y)
    if (!Number.isFinite(xNorm) || !Number.isFinite(yNorm)) {
      continue
    }
    const point = projectPoint(geometry, xNorm, yNorm)
    const radius = 5.5 * point.scale + 2.8
    const color = AVATAR_COLORS[avatarId] ?? '#9cb0cb'

    ctx.beginPath()
    ctx.arc(point.x, point.y, radius * 2.2, 0, Math.PI * 2)
    ctx.fillStyle = rgbaFromHex(color, 0.1)
    ctx.fill()

    ctx.beginPath()
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2)
    ctx.fillStyle = rgbaFromHex(color, 0.9)
    ctx.fill()
    ctx.lineWidth = 1
    ctx.strokeStyle = rgbaFromHex('#f6fbff', 0.52)
    ctx.stroke()

    const label = avatarId.slice(0, 3).toUpperCase()
    ctx.font = `${Math.max(10, radius * 1.25)}px "Space Grotesk", "Segoe UI", sans-serif`
    ctx.fillStyle = rgbaFromHex('#d8e8ff', 0.8)
    ctx.fillText(label, point.x + radius + 3, point.y + radius * 0.32)
  }
}

function drawHud(ctx, width, height, data) {
  const x = width * 0.025
  const y = height * 0.03
  const panelWidth = Math.max(280, width * 0.36)
  const panelHeight = Math.max(80, height * 0.12)

  drawRoundedRect(ctx, x, y, panelWidth, panelHeight, 8)
  ctx.fillStyle = rgbaFromHex('#0d151f', 0.72)
  ctx.fill()
  ctx.strokeStyle = rgbaFromHex('#5d7898', 0.45)
  ctx.lineWidth = 1.2
  ctx.stroke()

  ctx.font = '12px "Space Grotesk", "Segoe UI", sans-serif'
  ctx.fillStyle = rgbaFromHex('#cfe2ff', 0.88)
  ctx.fillText('CAM-04 / OFFICE FLOOR', x + 10, y + 18)

  ctx.fillStyle = rgbaFromHex('#9fb5d6', 0.88)
  ctx.fillText(`timestamp: ${data.timestamp}`, x + 10, y + 36)
  ctx.fillText(`queue: ${data.queueSize} | event: ${data.eventType}`, x + 10, y + 53)
  ctx.fillText(`stream: ${data.connectionState}`, x + 10, y + 70)
}

function drawScanlines(ctx, width, height) {
  ctx.strokeStyle = 'rgba(156, 184, 218, 0.06)'
  ctx.lineWidth = 1
  for (let y = 0; y < height; y += 4) {
    ctx.beginPath()
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(width, y + 0.5)
    ctx.stroke()
  }
}

function drawVignette(ctx, width, height) {
  const gradient = ctx.createRadialGradient(
    width * 0.5,
    height * 0.5,
    Math.min(width, height) * 0.2,
    width * 0.5,
    height * 0.5,
    Math.max(width, height) * 0.75,
  )
  gradient.addColorStop(0, 'rgba(0, 0, 0, 0)')
  gradient.addColorStop(1, 'rgba(0, 0, 0, 0.52)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)
}

function drawStatusOverlay(ctx, width, height, text, tone) {
  ctx.fillStyle = tone === 'alert' ? 'rgba(51, 6, 10, 0.72)' : 'rgba(6, 10, 18, 0.58)'
  ctx.fillRect(0, 0, width, height)
  ctx.font = `700 ${Math.max(28, width * 0.05)}px "Space Grotesk", "Segoe UI", sans-serif`
  ctx.fillStyle = tone === 'alert' ? rgbaFromHex('#ff7f8a', 0.95) : rgbaFromHex('#d8e6ff', 0.9)
  const textWidth = ctx.measureText(text).width
  ctx.fillText(text, width * 0.5 - textWidth * 0.5, height * 0.54)
}

function safeTimestamp(value) {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value
  }
  return new Date().toISOString()
}

export function drawOfficeScene(ctx, width, height, frame) {
  const animationState = isRecord(frame?.animationState) ? frame.animationState : {}
  const view = isRecord(frame?.view) ? frame.view : {}

  const lightLevel = clamp(Number(animationState.lightLevel) || 0.4, 0.2, 0.92)
  const stressLevel = clamp(Number(animationState.stressLevel) || 0, 0, 1)
  const queueSize = Number.isFinite(Number(view.event_queue_size))
    ? Number(view.event_queue_size)
    : Number(animationState.queueSize) || 0
  const running = Boolean(view.running ?? animationState.running)
  const eventType =
    typeof view?.current_event?.type === 'string' && view.current_event.type.length > 0
      ? view.current_event.type
      : animationState.currentEventType ?? 'none'

  drawBackdrop(ctx, width, height, lightLevel, stressLevel)

  const geometry = roomGeometry(width, height)
  drawRoomShell(ctx, geometry, lightLevel)
  drawFloorGrid(ctx, geometry, lightLevel)

  drawBoardroomTable(ctx, geometry, width, height, lightLevel)
  for (const desk of DESK_DEFINITIONS) {
    drawDesk(ctx, geometry, width, height, desk.zone, desk.monitorColor, lightLevel)
  }
  drawWaterCooler(ctx, geometry, width, height)

  const pulseList = Array.isArray(animationState.pulses) ? animationState.pulses : []
  drawZonePulses(ctx, geometry, pulseList)

  let securityPulseIntensity = 0
  let securityPulseColor = '#56cf88'
  for (const pulse of pulseList) {
    if (isRecord(pulse) && pulse.zone === 'securityCheckpoint') {
      securityPulseIntensity = Math.max(securityPulseIntensity, clamp(Number(pulse.intensity), 0, 1))
      if (typeof pulse.color === 'string') {
        securityPulseColor = pulse.color
      }
    }
  }
  drawSecurityCheckpoint(ctx, geometry, width, height, securityPulseIntensity, securityPulseColor)
  drawAvatars(ctx, geometry, animationState.avatars)

  const ambientPulse = clamp(Number(animationState.ambientPulse) || 0, 0, 1)
  if (ambientPulse > 0.01) {
    const pulse = ctx.createRadialGradient(
      width * 0.5,
      height * 0.5,
      0,
      width * 0.5,
      height * 0.5,
      width * 0.45,
    )
    pulse.addColorStop(0, rgbaFromHex('#7ea9df', 0.08 * ambientPulse))
    pulse.addColorStop(1, 'rgba(0, 0, 0, 0)')
    ctx.fillStyle = pulse
    ctx.fillRect(0, 0, width, height)
  }

  const timestamp = safeTimestamp(view.last_updated_at ?? view.timestamp ?? frame?.lastUpdated)
  drawHud(ctx, width, height, {
    timestamp,
    queueSize,
    eventType,
    connectionState: frame?.connectionState ?? 'unknown',
  })

  drawScanlines(ctx, width, height)
  drawVignette(ctx, width, height)

  if (!running && !frame?.signalLost) {
    drawStatusOverlay(ctx, width, height, 'PAUSED', 'neutral')
  }
  if (frame?.signalLost) {
    drawStatusOverlay(ctx, width, height, 'SIGNAL LOST', 'alert')
  }
}

export function createOfficeSceneRenderer(canvas) {
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) {
    return {
      render: () => {},
      resize: () => {},
      destroy: () => {},
    }
  }

  const viewport = {
    width: 0,
    height: 0,
    dpr: 1,
  }
  let disposed = false

  const ensureCanvasSize = () => {
    if (disposed) {
      return
    }
    const rect = canvas.getBoundingClientRect()
    const width = Math.max(1, Math.floor(rect.width))
    const height = Math.max(1, Math.floor(rect.height))
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    const desiredWidth = Math.max(1, Math.floor(width * dpr))
    const desiredHeight = Math.max(1, Math.floor(height * dpr))
    if (canvas.width !== desiredWidth || canvas.height !== desiredHeight) {
      canvas.width = desiredWidth
      canvas.height = desiredHeight
    }

    viewport.width = width
    viewport.height = height
    viewport.dpr = dpr
  }

  const render = (frame) => {
    ensureCanvasSize()
    context.setTransform(viewport.dpr, 0, 0, viewport.dpr, 0, 0)
    drawOfficeScene(context, viewport.width, viewport.height, frame)
  }

  const resize = () => {
    ensureCanvasSize()
  }

  const destroy = () => {
    disposed = true
  }

  return {
    render,
    resize,
    destroy,
  }
}
