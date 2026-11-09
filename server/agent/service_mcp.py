"""Shared MCP transport for session services and trusted background operations.

Handlers and credentials are supplied by the host, never by model arguments.
All streams belong to the caller task; cancellation tears down the operation.
"""
import asyncio
import json
import time

from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session

import debug_log

EMPTY_INPUT = {'type': 'object', 'properties': {}, 'additionalProperties': False}


class ServiceError(Exception):
    pass


async def call_service(service, operation, handler, *, schema=None, arguments=None,
                       timeout=90, max_chars=16000, call_id=None):
    """Invoke a host-bound operation through actual MCP schema validation.

    An argument-free closure can bind trusted objects (speaker, HTTP session,
    image bytes); those objects are not serialized or exposed to the LLM.
    """
    server = Server('ciel-' + service)
    failure = []

    @server.list_tools()
    async def listing():
        return [types.Tool(name=operation, description=operation, inputSchema=schema or EMPTY_INPUT)]

    @server.call_tool()
    async def execute(name, args):
        if name != operation:
            raise ValueError('unknown_operation')
        try:
            value = await handler(args)
            if len(json.dumps(value, ensure_ascii=False)) > max_chars:
                raise ServiceError('result_too_large')
            return {'value': value}
        except Exception as exc:
            # Preserve local retry semantics without putting private exceptions on the wire.
            failure.append(exc)
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='operation_failed')])

    started, status = time.monotonic(), 'failed'
    try:
        async with asyncio.timeout(timeout):
            async with create_connected_server_and_client_session(server) as client:
                result = await client.call_tool(operation, arguments if arguments is not None else {})
                packet = None if result.isError else result.structuredContent
        # Raise outside SDK task groups, preserving the caller's exception type.
        if failure:
            raise failure[0]
        if packet is None or 'value' not in packet:
            raise ServiceError('invalid_service_response')
        status = 'transport_completed'
        return packet['value']
    except asyncio.CancelledError:
        status = 'cancelled'
        raise
    except TimeoutError:
        status = 'timed_out'
        raise
    finally:
        debug_log.record('service_call', service=service, operation=operation, status=status,
                         call_id=call_id, seconds=round(time.monotonic() - started, 4))
