"""Expose blocked startup frames in isolated benchmarks without changing agent behavior."""
import asyncio
import debug_log
from agent import server, entrypoint




async def observed_entrypoint(ctx):
    async def diagnose():
        await asyncio.sleep(5)
        tasks = []
        for task in asyncio.all_tasks():
            frames = []
            coroutine = task.get_coro()
            for _ in range(20):
                frame = getattr(coroutine, 'cr_frame', None)
                if frame:
                    frames.append(f'{frame.f_code.co_filename}:{frame.f_lineno}:{frame.f_code.co_name}')
                coroutine = getattr(coroutine, 'cr_await', None)
                if coroutine is None:
                    break
            tasks.append({'name': task.get_name(), 'frames': frames})
        debug_log.record('benchmark_startup_wait', tasks=tasks)
    probe = asyncio.create_task(diagnose())
    try:
        return await entrypoint(ctx)
    finally:
        probe.cancel()
        await asyncio.gather(probe, return_exceptions=True)


server._entrypoint_fnc = observed_entrypoint
