import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateFindings, validateManifest, verifyVisualEvidence } from './s2cVerification.mjs'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const reviewRoot = path.resolve(testDir, '../../APP_SHAK_HANDOVER/S2C_VISUAL_REVIEW')
const manifest = JSON.parse(readFileSync(path.join(reviewRoot, 'manifest.json'), 'utf8'))
const findings = JSON.parse(readFileSync(path.join(reviewRoot, 'findings.json'), 'utf8'))
validateManifest(manifest)
validateFindings(findings)

const chromeCandidates = [
  process.env.APPSHAK_CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)
const chrome = chromeCandidates.find((candidate) => existsSync(candidate))
if (!chrome) throw new Error('Chrome or Edge is required for the S2C browser audit')

const baseUrl = process.env.APPSHAK_VISUAL_URL ?? 'http://127.0.0.1:4173'
const viewports = [
  { name: 'desktop', width: 1280, height: 760 },
  // Headless Chrome clamps narrower window requests to a 500px viewport.
  { name: 'compact', width: 500, height: 844 },
]

function browserArgs(viewport, url, extra = []) {
  return [
    '--headless=new', '--disable-gpu', '--hide-scrollbars',
    '--force-device-scale-factor=1', '--virtual-time-budget=3500',
    `--window-size=${viewport.width},${viewport.height}`,
    ...extra, url,
  ]
}

function runChrome(args) {
  return execFileSync(chrome, args, {
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'ignore'],
  })
}

function readObservation(entry, viewport) {
  const url = `${baseUrl}/tests/s2bVisualBaseline.html?scenario=${encodeURIComponent(entry.fixture)}`
  const html = runChrome(browserArgs(viewport, url, ['--dump-dom']))
  const match = html.match(/<script id="s2c-audit" type="application\/json">([\s\S]*?)<\/script>/)
  if (!match || !match[1]) throw new Error(`Browser fixture did not render: ${entry.fixture} / ${viewport.name}`)
  return JSON.parse(match[1])
}

function verifyBaseline(entry) {
  const image = path.resolve(reviewRoot, entry.baseline_image)
  const bytes = readFileSync(image)
  const sha256 = createHash('sha256').update(bytes).digest('hex')
  if (sha256 !== entry.baseline_sha256) {
    throw new Error(`S2B baseline hash changed: ${entry.fixture}`)
  }
  return { image: entry.baseline_image, sha256 }
}

const images = path.join(reviewRoot, 'images')
mkdirSync(images, { recursive: true })
const states = []
for (const entry of manifest.states) {
  const baseline = verifyBaseline(entry)
  const checks = {}
  for (const viewport of viewports) {
    const observation = readObservation(entry, viewport)
    checks[viewport.name] = {
      observed: observation,
      result: verifyVisualEvidence(entry, observation),
    }
  }
  const screenshotUrl = `${baseUrl}/tests/s2bVisualBaseline.html?scenario=${encodeURIComponent(entry.fixture)}`
  const screenshotPath = path.join(reviewRoot, entry.review_image)
  runChrome(browserArgs(viewports[0], screenshotUrl, [`--screenshot=${screenshotPath}`]))
  states.push({
    fixture: entry.fixture,
    ats_fixture: entry.ats,
    baseline,
    screenshot: entry.review_image,
    semantic_assertions: checks.desktop.result.semantic,
    structural_checks: Object.fromEntries(
      viewports.map((viewport) => [viewport.name, checks[viewport.name].result.structural]),
    ),
    measurements: Object.fromEntries(viewports.map((viewport) => {
      const observed = checks[viewport.name].observed
      return [viewport.name, {
        office_viewport: observed.render.viewport,
        browser_canvas: observed.browser.canvas,
        browser_viewport_width: observed.browser.viewport_width,
        document_width: observed.browser.document_width,
        hud_bounds: observed.render.hud?.bounds ?? null,
        marker_bounds: observed.render.marker?.markerBounds ?? null,
        status_label_bounds: observed.render.marker?.labelBounds ?? null,
        stale_overlay_text_bounds: observed.render.overlay?.textBounds ?? null,
      }]
    })),
    semantic_pass: viewports.every((viewport) => checks[viewport.name].result.semantic_pass),
    structural_pass: viewports.every((viewport) => checks[viewport.name].result.structural_pass),
    known_limitations: findings.filter((finding) =>
      finding.fixture === 'all' || finding.fixture.split(',').includes(entry.fixture),
    ).map((finding) => finding.finding_id),
    human_review_status: 'PENDING_OWNER_ACCEPTANCE',
  })
}

const review = {
  schema_version: 1,
  manifest: 'manifest.json',
  baseline_commit: manifest.baseline_commit,
  viewports,
  semantic_certified: states.every((state) => state.semantic_pass),
  structural_certified: states.every((state) => state.structural_pass),
  perceptual_reviewed: findings.length > 0,
  human_accepted: false,
  states,
}
writeFileSync(path.join(reviewRoot, 'review.json'), `${JSON.stringify(review, null, 2)}\n`, 'utf8')
for (const state of states) {
  process.stdout.write(`${state.fixture}: semantic=${state.semantic_pass ? 'PASS' : 'FAIL'} structural=${state.structural_pass ? 'PASS' : 'FAIL'}\n`)
}
if (!review.semantic_certified || !review.structural_certified) process.exitCode = 1
