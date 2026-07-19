# AppShak — Environment Setup Guide
**Phase 3B Certification — New Machine Checklist**
> Follow this top to bottom. No skipping. Estimated time: 10–15 minutes.

---

## STEP 1 — Prerequisites (Install Once)

Before proceeding, read [CURRENT_STATUS.md](CURRENT_STATUS.md) for the factual
repository maturity and certification position. The full document map is in
[docs/INDEX.md](docs/INDEX.md); dependency scope is documented in
[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

### Python
- Required: **Python 3.10 or higher**
- Check: `python --version`
- Download: https://www.python.org/downloads/
- ⚠️ On Windows: tick **"Add Python to PATH"** during install

### Git
- Check: `git --version`
- Download: https://git-scm.com/downloads
- ⚠️ On Windows: use default install options

### Node.js (for appshak-ui only)
- Required: **Node 18+**
- Check: `node --version`
- Download: https://nodejs.org/en (LTS version)

---

## STEP 2 — Clone the Repo

```bash
git clone https://github.com/LeiEugeb-ballz/AppShak_HQ.git
cd AppShak_HQ
```

---

## STEP 3 — Create Virtual Environment

```bash
python -m venv venv
```

Activate it:

| Platform | Command |
|----------|---------|
| Windows  | `venv\Scripts\activate` |
| Mac/Linux | `source venv/bin/activate` |

You should see `(venv)` in your terminal prompt. If you don't, stop and fix this before continuing.

---

## STEP 4 — Install Dependencies

```bash
pip install fastapi uvicorn[standard] websockets aiofiles
```

Verify:
```bash
pip show fastapi uvicorn websockets
```
All 3 should return version info. If any fail, re-run the install for that package.

---

## STEP 5 — Create Required State Directories

```bash
python -c "
import os
dirs = [
    'appshak_state/substrate',
    'appshak_state/projection',
    'appshak_state/governance',
    'appshak_state/integrity',
    'appshak_state/inspection',
    'appshak_state/stability',
    'appshak_state/agents',
    'workspaces'
]
for d in dirs:
    os.makedirs(d, exist_ok=True)
    print(f'OK: {d}')
print('All directories ready.')
"
```

All lines should print `OK:`. If any error appears, check your working directory — you must be inside `AppShak_HQ`.

---

## STEP 6 — Smoke Test (Quick Sanity Check)

Run the chambers first — these are fast and will catch broken installs immediately:

```bash
python -m appshak_substrate.chambers.chamber_a_durability
python -m appshak_substrate.chambers.chamber_b_isolation
python -m appshak_substrate.chambers.chamber_c_tool_enforcement
```

✅ Each should print `PASS`
❌ If any print `FAIL` — **do not proceed to the 6h run**. Report the failure output.

---

## STEP 7 — Run the Full Unit Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

All tests should pass. Note any failures — these must be resolved before certification.

---

## STEP 8 — (Optional) Launch the UI

In a separate terminal:
```bash
cd appshak-ui
npm install
npm run dev
```
Open: http://127.0.0.1:5173

---

## ✅ Environment Ready Checklist

Before starting the 6-hour certification run, confirm all of these:

- [ ] `python --version` shows 3.10+
- [ ] `(venv)` is active in terminal
- [ ] All `pip show` checks passed
- [ ] All state directories created
- [ ] All 3 chambers print `PASS`
- [ ] All unit tests pass
- [ ] Machine will not sleep/hibernate during the run (disable power saving!)
- [ ] Machine is plugged in (not on battery)
- [ ] No other heavy processes running

---

## ⚠️ Common Issues

| Problem | Fix |
|---------|-----|
| `python` not found | Use `python3` instead, or fix PATH |
| `ModuleNotFoundError` | Make sure venv is activated |
| Chamber `FAIL` on isolation | Check git is installed and accessible |
| Port 8010 already in use | `kill` the process using that port first |
| Projection view not found | Re-run Step 5 to create state directories |

---

*Once all boxes above are ticked, proceed to `CERTIFICATION_HARNESS.py`*
