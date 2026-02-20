import asyncio
from appshak import AppShakKernel
from appshak_office import SprintArena

async def main():
    kernel = AppShakKernel({"memory_root": "appshak_state"})
    arena = SprintArena(kernel=kernel, seed=12345)
    await arena.run_consecutive_sprints(count=10, seed=12345)
    arena.export_history("appshak_state/startup_sprint_history_export.json")

asyncio.run(main())
