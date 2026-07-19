# AppShak Observability UI (Phase 3.1)

Read-only React dashboard connected to:

For backend/UI run order, start at the repository [README](../README.md). Use
[CURRENT_STATUS.md](../CURRENT_STATUS.md) for maturity and
[docs/INDEX.md](../docs/INDEX.md) for documentation navigation.

- `GET http://127.0.0.1:8010/api/snapshot`
- `ws://127.0.0.1:8010/ws/events`

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
- `Office View` (read-only CCTV-style office visualization driven by projection state)

`Office View` consumes:

- `GET http://127.0.0.1:8010/api/snapshot` (2s poll fallback)
- `ws://127.0.0.1:8010/ws/events` filtered to `channel=view_update`

For Node requirements and package ownership, see
[docs/DEPENDENCIES.md](../docs/DEPENDENCIES.md).
