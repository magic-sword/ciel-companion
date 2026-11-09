"""Trusted memory maintenance, separate from model-visible memory tools.

The worker binds its verified speaker/snapshot in the handler. There is no
model-visible actor ID, raw SQL, or alternate Store access policy here.
"""
from service_mcp import call_service


OPERATIONS = frozenset({'consolidate_notes', 'revise_relationship', 'grow_preferences', 'record_event', 'load_events'})


async def run_memory_job(operation, handler):
    if operation not in OPERATIONS:
        raise ValueError('unsupported_memory_operation')
    async def execute(arguments):
        return await handler()
    return await call_service('memory', operation, execute)
