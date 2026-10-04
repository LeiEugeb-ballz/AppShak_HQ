const REQUIRED_FIXTURES = [
  'active', 'validation_failed', 'needs_reconciliation',
  'complete', 'waiting_for_capability', 'stale_unavailable',
]

const FINDING_CATEGORIES = new Set(['SEMANTIC', 'STRUCTURAL', 'PERCEPTUAL'])
const FINDING_SEVERITIES = new Set(['BLOCKER', 'MAJOR', 'MINOR'])
const FINDING_STATUSES = new Set(['OPEN', 'FIXED', 'ACCEPTED_FOR_S2E'])
const FINDING_KEYS = new Set([
  'finding_id', 'fixture', 'category', 'severity', 'description',
  'evidence', 'recommended_bounded_correction', 'status',
])

function check(list, name, passed, detail = null) {
  list.push({ name, passed: Boolean(passed), detail })
}

function inside(rect, width, height) {
  return rect && Number.isFinite(rect.x) && Number.isFinite(rect.y) &&
    Number.isFinite(rect.width) && Number.isFinite(rect.height) &&
    rect.x >= -1 && rect.y >= -1 && rect.width > 0 && rect.height > 0 &&
    rect.x + rect.width <= width + 1 && rect.y + rect.height <= height + 1
}

function overlaps(left, right) {
  return left && right && left.x < right.x + right.width &&
    left.x + left.width > right.x && left.y < right.y + right.height &&
    left.y + left.height > right.y
}

export function validateManifest(manifest) {
  const states = manifest?.states
  if (!Array.isArray(states) || states.length !== REQUIRED_FIXTURES.length) {
    throw new Error('Visual manifest must contain exactly six fixtures')
  }
  const names = states.map((entry) => entry.fixture)
  if (new Set(names).size !== names.length || REQUIRED_FIXTURES.some((name) => !names.includes(name))) {
    throw new Error('Visual manifest fixture names are incomplete or duplicated')
  }
  for (const entry of states) {
    if (!entry.ats || !entry.expected_visual_state || !entry.baseline_image ||
        !entry.baseline_sha256 || !entry.review_image || !entry.expected_zone ||
        !entry.expected_status_label || !Array.isArray(entry.allowed_worker_ids) ||
        !entry.expected_freshness || !entry.semantic_assertions) {
      throw new Error(`Incomplete visual manifest entry: ${entry.fixture}`)
    }
  }
  return true
}

export function validateFindings(findings) {
  if (!Array.isArray(findings)) throw new Error('Findings must be an array')
  const ids = new Set()
  for (const finding of findings) {
    if (Object.keys(finding).some((key) => !FINDING_KEYS.has(key)) ||
        !finding.finding_id || ids.has(finding.finding_id) ||
        !FINDING_CATEGORIES.has(finding.category) ||
        !FINDING_SEVERITIES.has(finding.severity) ||
        !FINDING_STATUSES.has(finding.status) ||
        !finding.description || !finding.evidence ||
        !finding.recommended_bounded_correction) {
      throw new Error(`Invalid bounded finding: ${finding.finding_id ?? 'unknown'}`)
    }
    ids.add(finding.finding_id)
  }
  return true
}

export function verifyVisualEvidence(entry, observation) {
  const semantic = []
  const structural = []
  const projection = observation?.projection ?? {}
  const render = observation?.render ?? {}
  const browser = observation?.browser ?? {}
  const marker = render.marker
  const overlay = render.overlay
  const viewport = render.viewport ?? {}
  const assertions = entry.semantic_assertions
  const ats = observation?.ats ?? {}

  check(semantic, 'ATS fixture binding',
    ['task_state', 'attempt_state', 'validation_state', 'dispatch_state', 'worker_id']
      .every((key) => ats[key] === entry.ats[key]))
  check(semantic, 'ATS-derived visual state',
    projection.state === entry.expected_visual_state && render.status === entry.expected_visual_state)
  check(semantic, 'freshness', projection.freshness === entry.expected_freshness)
  check(semantic, 'expected zone', projection.zone === entry.expected_zone)
  check(semantic, 'status label', render.hud?.statusLabel === entry.expected_status_label &&
    (marker?.label ?? overlay?.text) === entry.expected_status_label)
  check(semantic, 'marker visibility', Boolean(marker) === assertions.marker_required)
  check(semantic, 'stale overlay visibility', Boolean(overlay) === assertions.overlay_required)
  const drawnWorkers = [...(render.drawnAvatars ?? [])].sort()
  check(semantic, 'allowed worker identity',
    JSON.stringify(drawnWorkers) === JSON.stringify([...entry.allowed_worker_ids].sort()) &&
    Boolean(projection.worker) === assertions.worker_visible)
  check(semantic, 'forbidden completion',
    !assertions.forbid_complete || (projection.state !== 'COMPLETE' && marker?.label !== 'COMPLETE'))
  check(semantic, 'no external pickup',
    !assertions.forbid_external_pickup ||
      (projection.state !== 'EXTERNAL_EXECUTING' &&
        (entry.fixture !== 'waiting_for_capability' || (projection.worker === null && drawnWorkers.length === 0))))

  const width = Number(viewport.width)
  const height = Number(viewport.height)
  check(structural, 'nonempty canvas viewport', Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0)
  check(structural, 'HUD inside office viewport', inside(render.hud?.bounds, width, height))
  check(structural, 'primary HUD status text fits',
    Number.isFinite(render.hud?.statusTextWidth) &&
    render.hud.statusTextWidth <= render.hud.bounds.width - 20)
  if (assertions.marker_required) {
    check(structural, 'marker inside office viewport', inside(marker?.markerBounds, width, height))
    check(structural, 'status label inside office viewport', inside(marker?.labelBounds, width, height))
    check(structural, 'status label text fits',
      Number.isFinite(marker?.textWidth) && marker.textWidth <= marker.labelBounds.width - 16)
    check(structural, 'primary labels do not overlap', !overlaps(marker?.labelBounds, render.hud?.bounds))
    check(structural, 'state has a text cue beyond color', marker?.label === entry.expected_status_label)
  }
  if (assertions.overlay_required) {
    check(structural, 'error overlay text inside office viewport', inside(overlay?.textBounds, width, height))
    check(structural, 'error overlay has visible text', overlay?.text === entry.expected_status_label)
  }
  check(structural, 'canvas in browser viewport',
    browser.canvas?.width > 0 && browser.canvas?.height > 0 &&
    browser.canvas.left >= -1 && browser.canvas.right <= browser.viewport_width + 1)
  check(structural, 'no horizontal document overflow',
    browser.document_width <= browser.viewport_width + 1)
  check(structural, 'no undefined primary labels',
    !/undefined|null|NaN/.test(String(render.status)) &&
    !/undefined|null|NaN/.test(String(marker?.label ?? overlay?.text)))

  return {
    semantic,
    structural,
    semantic_pass: semantic.every((item) => item.passed),
    structural_pass: structural.every((item) => item.passed),
  }
}
