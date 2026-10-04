import { clamp, lerp } from './effects.js'

// Stable locations are presentation coordinates, never task or worker state.
export const OFFICE_ZONES = {
  supervisorDesk: { x: 0.79, y: 0.25, label: 'SUPERVISION' },
  commandDesk: { x: 0.18, y: 0.47, label: 'COMMAND' },
  reconDesk: { x: 0.2, y: 0.8, label: 'INCIDENT REVIEW' },
  forgeDesk: { x: 0.79, y: 0.8, label: 'DELIVERY ARCHIVE' },
  boardroom: { x: 0.53, y: 0.61, label: 'VALIDATION' },
  dispatchZone: { x: 0.39, y: 0.3, label: 'CAPABILITY HANDOFF' },
  waterCooler: { x: 0.92, y: 0.12, label: 'FACILITIES' },
  securityCheckpoint: { x: 0.06, y: 0.32, label: 'ENTRY' },
  supervisorIdle: { x: 0.62, y: 0.26, label: 'SUPERVISION' },
}

const C = {
  ink: '#101923', wall: '#202b35', floor: '#303c45', floorLow: '#26323c',
  edge: '#60717b', ivory: '#f0eadb', muted: '#b5c4c9', brass: '#d6b77b',
  teal: '#8ccbbd', coral: '#e6a088', incident: '#e8b680',
}

const STATE_COLOR = {
  'ACTIVE / EXECUTING': C.teal,
  'VALIDATION IN PROGRESS': C.brass,
  VALIDATION_PENDING: C.brass,
  RESULT_RETURNED: C.brass,
  VALIDATION_FAILED: C.coral,
  VALIDATION_ERROR: C.coral,
  EXECUTION_FAILED: C.coral,
  HANDOFF_FAILED: C.coral,
  NEEDS_RECONCILIATION: C.incident,
  WAITING_FOR_CAPABILITY: C.brass,
  HANDOFF_DISPATCHED: C.teal,
  EXTERNAL_PICKUP_ACKNOWLEDGED: C.teal,
  EXTERNAL_RUNNING: C.teal,
  COMPLETE: '#a9d5b6',
}

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function rgba(hex, alpha) {
  const clean = String(hex).replace('#', '')
  const value = clean.length === 6 ? clean : 'ffffff'
  return `rgba(${Number.parseInt(value.slice(0, 2), 16)}, ${Number.parseInt(value.slice(2, 4), 16)}, ${Number.parseInt(value.slice(4, 6), 16)}, ${clamp(alpha, 0, 1)})`
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2)
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + width - r, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + r)
  ctx.lineTo(x + width, y + height - r)
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
  ctx.lineTo(x + r, y + height)
  ctx.quadraticCurveTo(x, y + height, x + r, y)
  ctx.closePath()
}

function panel(ctx, x, y, width, height, fill, stroke, radius = 10) {
  roundRect(ctx, x, y, width, height, radius)
  ctx.fillStyle = fill
  ctx.fill()
  if (stroke) {
    ctx.lineWidth = 1
    ctx.strokeStyle = stroke
    ctx.stroke()
  }
}

function geometryFor(width, height) {
  return {
    top: height * 0.14, bottom: height * 0.94,
    leftTop: width * 0.13, rightTop: width * 0.87,
    leftBottom: width * 0.035, rightBottom: width * 0.965,
  }
}

function projectPoint(geometry, xNorm, yNorm) {
  const y = clamp(yNorm, 0, 1)
  const left = lerp(geometry.leftTop, geometry.leftBottom, y)
  const right = lerp(geometry.rightTop, geometry.rightBottom, y)
  return { x: lerp(left, right, clamp(xNorm, 0, 1)),
    y: lerp(geometry.top, geometry.bottom, y), scale: lerp(0.77, 1.12, y) }
}

function drawRoom(ctx, width, height, geometry) {
  const background = ctx.createLinearGradient(0, 0, 0, height)
  background.addColorStop(0, '#111d27')
  background.addColorStop(1, '#0b141d')
  ctx.fillStyle = background
  ctx.fillRect(0, 0, width, height)

  const wallY = geometry.top - 27
  ctx.fillStyle = C.wall
  ctx.fillRect(geometry.leftTop, wallY, geometry.rightTop - geometry.leftTop, 30)
  ctx.fillStyle = '#374853'
  ctx.fillRect(geometry.leftTop, wallY + 26, geometry.rightTop - geometry.leftTop, 3)
  for (let index = 1; index <= 3; index += 1) {
    const x = lerp(geometry.leftTop, geometry.rightTop, index / 4)
    ctx.fillStyle = '#283641'
    ctx.fillRect(x, wallY + 3, 2, 23)
  }

  ctx.beginPath()
  ctx.moveTo(geometry.leftTop, geometry.top)
  ctx.lineTo(geometry.rightTop, geometry.top)
  ctx.lineTo(geometry.rightBottom, geometry.bottom)
  ctx.lineTo(geometry.leftBottom, geometry.bottom)
  ctx.closePath()
  const floor = ctx.createLinearGradient(0, geometry.top, 0, geometry.bottom)
  floor.addColorStop(0, C.floor)
  floor.addColorStop(1, C.floorLow)
  ctx.fillStyle = floor
  ctx.fill()
  ctx.lineWidth = 2
  ctx.strokeStyle = C.edge
  ctx.stroke()

  // Broad floor seams give the room scale without a diagnostic grid.
  for (const yNorm of [0.24, 0.53, 0.79]) {
    const left = projectPoint(geometry, 0, yNorm)
    const right = projectPoint(geometry, 1, yNorm)
    ctx.beginPath()
    ctx.moveTo(left.x, left.y)
    ctx.lineTo(right.x, right.y)
    ctx.strokeStyle = rgba('#9daeb0', 0.11)
    ctx.lineWidth = 1
    ctx.stroke()
  }
  for (const xNorm of [0.32, 0.66]) {
    const top = projectPoint(geometry, xNorm, 0)
    const bottom = projectPoint(geometry, xNorm, 1)
    ctx.beginPath()
    ctx.moveTo(top.x, top.y)
    ctx.lineTo(bottom.x, bottom.y)
    ctx.strokeStyle = rgba('#9daeb0', 0.09)
    ctx.stroke()
  }
}

function zoneLabel(ctx, geometry, zoneName, width, height) {
  const zone = OFFICE_ZONES[zoneName]
  const p = projectPoint(geometry, zone.x, zone.y)
  const compact = width < 650
  const short = {
    supervisorDesk: 'SUPERVISION', commandDesk: 'COMMAND', reconDesk: 'REVIEW',
    forgeDesk: 'ARCHIVE', boardroom: 'QA', dispatchZone: 'HANDOFF',
  }
  const label = compact ? short[zoneName] : zone.label
  ctx.font = `700 ${compact ? 9 : 11}px "Bahnschrift", "Trebuchet MS", sans-serif`
  const textWidth = ctx.measureText(label).width
  const x = clamp(p.x - textWidth / 2, 8, width - textWidth - 8)
  const y = p.y + Math.max(38, height * 0.075) * p.scale
  ctx.fillStyle = rgba(C.ivory, 0.76)
  ctx.fillText(label, x, y)
  return { zone: zoneName, label, bounds: { x, y: y - 12, width: textWidth, height: 15 } }
}

function drawDesk(ctx, geometry, zoneName, width, height, tone) {
  const zone = OFFICE_ZONES[zoneName]
  const p = projectPoint(geometry, zone.x, zone.y)
  const deskWidth = Math.max(54, Math.min(116, width * 0.105)) * p.scale
  const deskHeight = Math.max(23, Math.min(42, height * 0.07)) * p.scale
  const x = p.x - deskWidth / 2
  const y = p.y - deskHeight / 2
  panel(ctx, x + 3, y + 8, deskWidth, deskHeight, rgba('#080e14', 0.32), null, 8)
  panel(ctx, x, y, deskWidth, deskHeight, '#52616a', rgba('#b3bfc0', 0.45), 7)
  panel(ctx, x + 5, y + 4, deskWidth - 10, deskHeight - 8, '#67757b', null, 5)
  const screenWidth = deskWidth * 0.35
  panel(ctx, p.x - screenWidth / 2, y - 16 * p.scale, screenWidth, 16 * p.scale,
    '#172732', rgba(tone, 0.8), 3)
  ctx.fillStyle = rgba(tone, 0.24)
  ctx.fillRect(p.x - screenWidth / 2 + 3, y - 13 * p.scale, screenWidth - 6, 9 * p.scale)
  panel(ctx, x + deskWidth * 0.12, y + deskHeight * 0.34, deskWidth * 0.26,
    deskHeight * 0.4, '#e1d8c4', null, 2)
  ctx.beginPath()
  ctx.ellipse(p.x, y + deskHeight + 12 * p.scale, deskWidth * 0.2, 7 * p.scale, 0, 0, Math.PI * 2)
  ctx.fillStyle = '#394a50'
  ctx.fill()
}

function drawValidationTable(ctx, geometry, width) {
  const p = projectPoint(geometry, OFFICE_ZONES.boardroom.x, OFFICE_ZONES.boardroom.y)
  const w = Math.max(68, Math.min(158, width * 0.14)) * p.scale
  panel(ctx, p.x - w / 2 + 3, p.y - 18, w, 43, rgba('#081117', 0.34), null, 12)
  panel(ctx, p.x - w / 2, p.y - 22, w, 43, '#596965', rgba(C.brass, 0.58), 10)
  panel(ctx, p.x - w * 0.29, p.y - 16, w * 0.31, 25, '#ede6d8', null, 3)
  ctx.fillStyle = '#637471'
  ctx.fillRect(p.x - w * 0.24, p.y - 8, w * 0.19, 2)
  ctx.fillRect(p.x - w * 0.24, p.y - 3, w * 0.15, 2)
  ctx.beginPath()
  ctx.arc(p.x + w * 0.24, p.y, 10 * p.scale, 0, Math.PI * 2)
  ctx.strokeStyle = C.brass
  ctx.lineWidth = 2
  ctx.stroke()
}

function drawDispatchDock(ctx, geometry, width) {
  const p = projectPoint(geometry, OFFICE_ZONES.dispatchZone.x, OFFICE_ZONES.dispatchZone.y)
  const w = Math.max(100, Math.min(220, width * 0.21)) * p.scale
  panel(ctx, p.x - w / 2, p.y - 16, w, 35 * p.scale, rgba('#25373a', 0.96), rgba(C.brass, 0.44), 8)
  const slotWidth = w * 0.33
  panel(ctx, p.x - w * 0.43, p.y - 9, slotWidth, 20 * p.scale, '#56615f', rgba(C.brass, 0.5), 3)
  panel(ctx, p.x + w * 0.09, p.y - 9, slotWidth, 20 * p.scale, '#56615f', rgba(C.teal, 0.5), 3)
  ctx.font = '700 9px "Bahnschrift", "Trebuchet MS", sans-serif'
  ctx.fillStyle = C.ivory
  ctx.fillText('HOLD', p.x - w * 0.41, p.y + 5)
  ctx.fillText('SEND', p.x + w * 0.11, p.y + 5)
}

function drawIncidentBoard(ctx, geometry) {
  const p = projectPoint(geometry, OFFICE_ZONES.reconDesk.x, OFFICE_ZONES.reconDesk.y)
  panel(ctx, p.x - 27 * p.scale, p.y - 29 * p.scale, 54 * p.scale, 45 * p.scale,
    '#695c4c', rgba(C.incident, 0.6), 4)
  panel(ctx, p.x - 20 * p.scale, p.y - 23 * p.scale, 40 * p.scale, 33 * p.scale,
    '#e3d8c1', null, 2)
  ctx.font = `700 ${14 * p.scale}px Georgia, serif`
  ctx.fillStyle = '#7c5641'
  ctx.fillText('?', p.x - 5 * p.scale, p.y + 2 * p.scale)
}

function drawArchive(ctx, geometry) {
  const p = projectPoint(geometry, OFFICE_ZONES.forgeDesk.x, OFFICE_ZONES.forgeDesk.y)
  panel(ctx, p.x - 31 * p.scale, p.y - 26 * p.scale, 62 * p.scale, 42 * p.scale,
    '#4b5c55', rgba('#b6d3bf', 0.55), 5)
  for (let index = 0; index < 3; index += 1) {
    panel(ctx, p.x - 23 * p.scale + index * 15 * p.scale, p.y - 17 * p.scale,
      12 * p.scale, 22 * p.scale, ['#b9cfc0', '#d6d7bc', '#98b6a8'][index], null, 2)
  }
}

function drawRoomObjects(ctx, geometry, width, height) {
  drawDesk(ctx, geometry, 'commandDesk', width, height, C.teal)
  drawDesk(ctx, geometry, 'supervisorDesk', width, height, C.brass)
  drawDispatchDock(ctx, geometry, width)
  drawValidationTable(ctx, geometry, width)
  drawIncidentBoard(ctx, geometry)
  drawArchive(ctx, geometry)
  return ['commandDesk', 'supervisorDesk', 'dispatchZone', 'boardroom', 'reconDesk', 'forgeDesk']
    .map((zone) => zoneLabel(ctx, geometry, zone, width, height))
}

function drawTravel(ctx, geometry, travel) {
  if (!isRecord(travel) || !isRecord(travel.from) || !isRecord(travel.target)) return null
  const start = projectPoint(geometry, travel.from.x, travel.from.y)
  const end = projectPoint(geometry, travel.target.x, travel.target.y)
  ctx.beginPath()
  ctx.moveTo(start.x, start.y)
  ctx.lineTo(end.x, end.y)
  ctx.strokeStyle = rgba(C.ivory, 0.6)
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(end.x, end.y, 8, 0, Math.PI * 2)
  ctx.strokeStyle = C.brass
  ctx.stroke()
  return { from: start, target: end, progress: travel.progress,
    fromZone: travel.fromZone, toZone: travel.toZone }
}

function drawAvatars(ctx, geometry, avatars, workers, width) {
  if (!isRecord(avatars)) return { ids: [], labels: [] }
  const ids = []
  const labels = []
  for (const worker of workers) {
    const position = avatars[worker.id]
    if (!isRecord(position) || !Number.isFinite(position.x) || !Number.isFinite(position.y)) continue
    const p = projectPoint(geometry, position.x, position.y)
    const size = 11 * p.scale
    ctx.beginPath()
    ctx.arc(p.x, p.y - size * 0.45, size * 0.53, 0, Math.PI * 2)
    ctx.fillStyle = C.ivory
    ctx.fill()
    panel(ctx, p.x - size * 0.8, p.y + size * 0.08, size * 1.6, size * 1.15,
      '#688b88', rgba(C.teal, 0.7), 5)
    const name = worker.id
    ctx.font = `700 ${width < 650 ? 10 : 12}px "Bahnschrift", "Trebuchet MS", sans-serif`
    const labelWidth = Math.min(150, ctx.measureText(name).width + 18)
    const x = clamp(p.x + size * 1.25, 7, width - labelWidth - 7)
    const y = p.y - 12
    panel(ctx, x, y, labelWidth, 25, '#172631', rgba(C.teal, 0.65), 5)
    ctx.fillStyle = C.ivory
    ctx.fillText(name, x + 9, y + 16)
    ids.push(worker.id)
    labels.push({ id: worker.id, text: name, bounds: { x, y, width: labelWidth, height: 25 } })
  }
  return { ids, labels }
}

function hudBounds(width, height) {
  return { x: width < 650 ? 13 : 22, y: height < 400 ? 10 : 16,
    width: Math.min(width - 26, width < 650 ? width * 0.94 : 422),
    height: height < 400 ? 94 : 105 }
}

function overlaps(a, b) {
  return a.x < b.x + b.width && a.x + a.width > b.x &&
    a.y < b.y + b.height && a.y + a.height > b.y
}

export function layoutWorkflowMarker(ctx, width, height, projection, position = null) {
  if (!projection?.live || !projection.taskId || !projection.workItem) return null
  const geometry = geometryFor(width, height)
  const item = position ?? projection.workItem
  const point = projectPoint(geometry, item.x, item.y)
  const label = projection.state
  ctx.font = `700 ${width < 650 ? 10 : 12}px "Bahnschrift", "Trebuchet MS", sans-serif`
  const textWidth = ctx.measureText(label).width
  const labelWidth = Math.min(width - 16, Math.max(92, Math.ceil(textWidth + 24)))
  const labelHeight = 26
  let labelBounds = {
    x: clamp(point.x - labelWidth / 2, 8, width - labelWidth - 8),
    y: point.y - 57 * point.scale,
    width: labelWidth, height: labelHeight,
  }
  if (overlaps(labelBounds, hudBounds(width, height)) || labelBounds.y < 8) {
    labelBounds = { ...labelBounds, y: point.y + 25 * point.scale }
  }
  return {
    zone: projection.zone, state: projection.state, label,
    labelBounds, textWidth,
    markerBounds: { x: point.x - 17 * point.scale, y: point.y - 17 * point.scale,
      width: 34 * point.scale, height: 34 * point.scale },
  }
}

function drawWorkflowMarker(ctx, width, height, projection, position) {
  const layout = layoutWorkflowMarker(ctx, width, height, projection, position)
  if (!layout) return null
  const marker = layout.markerBounds
  const color = STATE_COLOR[projection.state] ?? C.muted
  const x = marker.x
  const y = marker.y
  panel(ctx, x + 3, y + 4, marker.width, marker.height, rgba('#08131a', 0.35), null, 5)
  panel(ctx, x, y, marker.width, marker.height, '#eee5d2', rgba(color, 0.9), 5)
  // The glyph supplies a second, non-color cue for each stage.
  const glyph = projection.state === 'COMPLETE' ? '✓'
    : projection.state === 'WAITING_FOR_CAPABILITY' ? 'Ⅱ'
      : ['NEEDS_RECONCILIATION', 'VALIDATION_FAILED', 'VALIDATION_ERROR',
        'EXECUTION_FAILED', 'HANDOFF_FAILED'].includes(projection.state) ? '!'
        : ['HANDOFF_DISPATCHED', 'EXTERNAL_PICKUP_ACKNOWLEDGED', 'EXTERNAL_RUNNING'].includes(projection.state) ? '↗'
          : ['VALIDATION_PENDING', 'VALIDATION IN PROGRESS', 'RESULT_RETURNED'].includes(projection.state) ? '≡' : '•'
  ctx.font = `700 ${Math.max(15, marker.height * 0.64)}px Georgia, serif`
  ctx.fillStyle = '#263942'
  ctx.textAlign = 'center'
  ctx.fillText(glyph, x + marker.width / 2, y + marker.height * 0.73)
  ctx.textAlign = 'start'

  const label = layout.labelBounds
  panel(ctx, label.x, label.y, label.width, label.height, '#15232e', rgba(color, 0.9), 6)
  ctx.font = `700 ${width < 650 ? 10 : 12}px "Bahnschrift", "Trebuchet MS", sans-serif`
  ctx.fillStyle = C.ivory
  ctx.textAlign = 'center'
  ctx.fillText(layout.label, label.x + label.width / 2, label.y + 18)
  ctx.textAlign = 'start'
  return { ...layout, glyph }
}

function drawHud(ctx, width, height, projection) {
  const bounds = hudBounds(width, height)
  panel(ctx, bounds.x, bounds.y, bounds.width, bounds.height, rgba(C.ink, 0.95), rgba(C.edge, 0.85), 9)
  ctx.fillStyle = C.brass
  ctx.fillRect(bounds.x, bounds.y, 5, bounds.height)
  ctx.font = '700 10px "Bahnschrift", "Trebuchet MS", sans-serif'
  ctx.fillStyle = C.muted
  ctx.fillText('APPSHAK   /   ATS OFFICE', bounds.x + 18, bounds.y + 19)
  ctx.font = '700 10px "Bahnschrift", "Trebuchet MS", sans-serif'
  const mode = projection.live ? 'LIVE • READ ONLY' : 'NOT LIVE • READ ONLY'
  const modeWidth = ctx.measureText(mode).width
  if (modeWidth + 32 < bounds.width) {
    ctx.fillStyle = projection.live ? C.teal : C.coral
    ctx.fillText(mode, bounds.x + bounds.width - modeWidth - 12, bounds.y + 19)
  }
  const status = projection.state ?? 'UNKNOWN_STATE'
  ctx.font = `700 ${width < 650 ? 12 : 15}px "Bahnschrift", "Trebuchet MS", sans-serif`
  const statusWidth = ctx.measureText(status).width
  ctx.fillStyle = C.ivory
  ctx.fillText(status, bounds.x + 18, bounds.y + 48)
  ctx.font = '11px "Bahnschrift", "Trebuchet MS", sans-serif'
  ctx.fillStyle = C.muted
  const taskText = projection.taskId ? `TASK  ${projection.taskId}` : 'NO CURRENT TASK'
  const taskMax = bounds.width - 32
  const visibleTask = ctx.measureText(taskText).width > taskMax
    ? `${taskText.slice(0, Math.max(10, Math.floor(taskMax / 7) - 3))}…` : taskText
  ctx.fillText(visibleTask, bounds.x + 18, bounds.y + 70)
  const workerText = projection.worker ? `WORKER  ${projection.worker.id}`
    : projection.handoffTarget ? `TARGET  ${projection.handoffTarget}` : 'WORKER  NONE CONFIRMED HERE'
  const visibleWorker = ctx.measureText(workerText).width > taskMax
    ? `${workerText.slice(0, Math.max(10, Math.floor(taskMax / 7) - 3))}…` : workerText
  ctx.fillText(visibleWorker, bounds.x + 18, bounds.y + 88)
  return { bounds, statusLabel: status, statusTextWidth: statusWidth,
    workerId: projection.worker?.id ?? null, taskId: projection.taskId ?? null }
}

function drawStatusOverlay(ctx, width, height, text) {
  ctx.fillStyle = rgba('#0b151e', 0.88)
  ctx.fillRect(0, 0, width, height)
  let fontSize = Math.max(23, Math.min(42, width * 0.048))
  ctx.font = `700 ${fontSize}px "Bahnschrift", "Trebuchet MS", sans-serif`
  while (ctx.measureText(text).width > width * 0.9 && fontSize > 15) {
    fontSize -= 1
    ctx.font = `700 ${fontSize}px "Bahnschrift", "Trebuchet MS", sans-serif`
  }
  const textWidth = ctx.measureText(text).width
  const baseline = height * 0.53
  ctx.fillStyle = C.ivory
  ctx.fillText(text, (width - textWidth) / 2, baseline)
  ctx.font = '700 12px "Bahnschrift", "Trebuchet MS", sans-serif'
  const note = 'LAST KNOWN STATE • LIVE MOVEMENT PAUSED'
  const noteWidth = ctx.measureText(note).width
  ctx.fillStyle = C.coral
  ctx.fillText(note, (width - noteWidth) / 2, baseline + 29)
  return { text, textBounds: { x: (width - textWidth) / 2, y: baseline - fontSize,
    width: textWidth, height: fontSize } }
}

export function drawOfficeScene(ctx, width, height, frame) {
  const animation = isRecord(frame?.animationState) ? frame.animationState : {}
  const projection = isRecord(animation.officeProjection) ? animation.officeProjection : {}
  const officeModel = isRecord(frame?.officeModel) ? frame.officeModel : {}
  const current = officeModel.freshness === 'LIVE / CURRENT' && projection.live
  const geometry = geometryFor(width, height)

  drawRoom(ctx, width, height, geometry)
  const zones = drawRoomObjects(ctx, geometry, width, height)
  const travel = current ? drawTravel(ctx, geometry, animation.travel) : null
  const avatars = current ? drawAvatars(ctx, geometry, animation.avatars, projection.workers ?? [], width)
    : { ids: [], labels: [] }
  const marker = current ? drawWorkflowMarker(ctx, width, height, projection, animation.workItemPosition) : null
  const hud = drawHud(ctx, width, height, projection)
  const overlay = current ? null
    : drawStatusOverlay(ctx, width, height, officeModel.availability ?? 'UNKNOWN_STATE')

  return {
    viewport: { width, height },
    status: projection.state ?? officeModel.scene_status ?? 'UNKNOWN_STATE',
    marker, hud, overlay,
    drawnAvatars: avatars.ids,
    workerLabels: avatars.labels,
    zones, travel,
    workItem: current ? animation.workItemPosition ?? projection.workItem : null,
  }
}

export function createOfficeSceneRenderer(canvas) {
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return { render: () => {}, resize: () => {}, destroy: () => {} }
  const viewport = { width: 0, height: 0, dpr: 1 }
  let disposed = false

  const ensureCanvasSize = () => {
    if (disposed) return
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

  return {
    render(frame) {
      ensureCanvasSize()
      context.setTransform(viewport.dpr, 0, 0, viewport.dpr, 0, 0)
      return drawOfficeScene(context, viewport.width, viewport.height, frame)
    },
    resize: ensureCanvasSize,
    destroy() { disposed = true },
  }
}
