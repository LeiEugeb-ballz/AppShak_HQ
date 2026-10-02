# AppShak Observability UI

Read-only React dashboard connected to observability telemetry and the S1
canonical office-state projection.

For backend/UI run order, start at the repository [README](../README.md). Use
[CURRENT_STATUS.md](../CURRENT_STATUS.md) for maturity and
[docs/INDEX.md](../docs/INDEX.md) for documentation navigation.

- `GET http://127.0.0.1:8010/api/snapshot`
- `ws://127.0.0.1:8010/ws/events`
- `GET http://127.0.0.1:8010/api/office/state`

## Run

```bash
npm install
npm run dev
```

Open:

`http://127.0.0.1:5173`

## Views

Use the top navigation to switch between:

- `Summary View` (status panel + event console)
- `Office View` (read-only CCTV-style visualization and canonical S1 workflow panel)

`Office View` consumes:

- `GET http://127.0.0.1:8010/api/snapshot` (2s poll fallback)
- `ws://127.0.0.1:8010/ws/events` filtered to `channel=view_update`
- `GET http://127.0.0.1:8010/api/office/state` for task, attempt, artifact,
  validation, baton, and routing truth. The backend must be started with
  `--mailstore-db` pointed at the intended S1 SQLite mailstore.

Run `npm run test:office` for the focused view-model and rendering tests. See
[S2A-WP1 Operator Console Binding](../APP_SHAK_HANDOVER/S2A_WP1_OPERATOR_CONSOLE_BINDING.md)
for stale/error behavior and screenshot provenance.

For Node requirements and package ownership, see
[docs/DEPENDENCIES.md](../docs/DEPENDENCIES.md).
