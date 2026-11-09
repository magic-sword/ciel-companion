"""MCP boundary for host-bound services, using the SDK's in-process transport.

Trusted RunContext stays in the host closure; it is never a tool argument.
These are session adapters, not network services or independent DB credentials.
"""
import asyncio
import json
import time

from livekit.agents import RunContext, ToolError, ToolResult, function_tool
from livekit.agents.llm import utils
from service_mcp import call_service

import debug_log


class SessionMCP:
    def __init__(self, catalog):
        self.catalog = catalog

    def wrap(self, original):
        schema = getattr(original.info, 'raw_schema', None) or utils.build_legacy_openai_schema(original)['function']
        schema = {**schema, 'parameters': dict(schema['parameters'])}
        schema['parameters']['additionalProperties'] = False

        async def invoke(raw_arguments: dict, context: RunContext):
            if original.id not in self.catalog.exposed:
                raise ToolError('この発言では公開されていない道具です。')
            return await self.call(original, schema, raw_arguments, context)

        return function_tool(invoke, raw_schema=schema)

    async def call(self, original, schema, arguments, context):
        async def execute(arguments):
            # Authorization is checked in the server too; loading a schema is insufficient.
            if original.id not in self.catalog.exposed:
                raise ValueError('tool_not_exposed')
            args, kwargs = utils.prepare_function_arguments(
                fnc=original, json_arguments=json.dumps(arguments), call_ctx=context)
            output = await original(*args, **kwargs)
            reply = True
            if isinstance(output, ToolResult):
                reply, output = output.reply_required, output.output
            encoded = json.dumps(output, ensure_ascii=False)
            if len(encoded) > 16000:
                output = {'status': 'truncated', 'summary': encoded[:7000], 'clipped': True}
            return {'output': output, 'reply_required': reply}

        started = time.monotonic()
        status = 'failed'
        try:
            packet = await call_service(self.catalog.service_for(original.id) or 'host', original.id, execute,
                                        schema=schema['parameters'], arguments=arguments,
                                        call_id=getattr(getattr(context, 'function_call', None), 'call_id', None))
            status = 'transport_completed'
            return ToolResult(packet['output'], reply_required=packet['reply_required'])
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except TimeoutError as exc:
            status = 'timed_out'
            raise ToolError('サービスの応答期限を超えました。実行結果は未確定なので状態を確認してください。') from exc
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError('MCPの通信に失敗しました。実行結果は未確定なので状態を確認してください。') from exc
        finally:
            debug_log.record('capability_call', service=self.catalog.service_for(original.id),
                             tool=original.id, status=status,
                             call_id=getattr(getattr(context, 'function_call', None), 'call_id', None),
                             seconds=round(time.monotonic() - started, 4))
