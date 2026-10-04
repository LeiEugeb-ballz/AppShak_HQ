import React, { useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import '../src/App.css'
import { OfficeAnimator } from '../src/office/animator.js'
import { createOfficeSceneRenderer } from '../src/office/scene.js'
import { createVisualScenario, VISUAL_SCENARIOS } from './s2cVisualFixtures.js'

const requested = new URLSearchParams(window.location.search).get('scenario')
const scenario = VISUAL_SCENARIOS.includes(requested) ? requested : 'active'
const { raw, model } = createVisualScenario(scenario)

export function Fixture() {
  const canvasRef = useRef(null)
  useEffect(() => {
    const canvas = canvasRef.current
    const renderer = createOfficeSceneRenderer(canvas)
    const animator = new OfficeAnimator()
    animator.ingestOfficeModel(model)
    const frame = animator.tick(1000)
    const evidence = renderer.render({ animationState: frame, officeModel: model, connectionState: 'fixture' })
    const result = {
      scenario,
      ats: {
        task_state: raw.tasks[0].state,
        attempt_state: raw.tasks[0].attempts[0].state,
        validation_state: raw.tasks[0].validations[0]?.status ?? null,
        dispatch_state: raw.batons[0]?.dispatch_status ?? null,
        worker_id: raw.tasks[0].assigned_agent,
      },
      projection: frame.officeProjection,
      render: evidence,
      browser: {
        canvas: canvas.getBoundingClientRect().toJSON(),
        viewport_width: window.innerWidth,
        document_width: document.documentElement.scrollWidth,
      },
    }
    document.getElementById('s2c-audit').textContent = JSON.stringify(result)
    document.body.dataset.s2cReady = 'true'
    return () => renderer.destroy()
  }, [])
  return <main className="dashboard"><header className="dashboard__header"><div><h1>AppShak Office · S2C</h1><p>ATS projection fixture: {scenario}</p></div></header><div className="office-view"><div className="office-view__canvas-shell"><canvas ref={canvasRef} className="office-view__canvas" aria-label={`S2C ${scenario} office baseline`} /></div></div></main>
}

createRoot(document.getElementById('root')).render(<Fixture />)
