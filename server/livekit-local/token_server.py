"""Tokens for the LiveKit server inside the home network (test only; docs/operations/local-livekit-ja.md).

The app's endpoint token source posts {"room_name": ..., "room_config": ...} and expects
{"server_url": ..., "participant_token": ...}, as LiveKit's sandbox token server answers. Each room
dispatches the test conversation server (LIVEKIT_LOCAL_AGENT) unless the request names agents itself.
Listens on the home address only; the keys come from server/.env.livekit-local.
"""
import json
import os
import re
import uuid

from aiohttp import web
from livekit import api

KEY, SECRET = os.environ['LIVEKIT_LOCAL_KEY'], os.environ['LIVEKIT_LOCAL_SECRET']
SERVER_URL = os.environ['LIVEKIT_LOCAL_URL']        # ws://<home address>:7880, as the app reaches it
AGENT = os.environ.get('LIVEKIT_LOCAL_AGENT', 'ciel-dev')
ROOM = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


async def token(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}
    room = str(body.get('room_name') or ('ciel-' + uuid.uuid4().hex))
    if not ROOM.match(room):
        return web.json_response({'error': 'bad room_name'}, status=400)
    agents = [a.get('agent_name') for a in ((body.get('room_config') or {}).get('agents') or []) if a.get('agent_name')]
    grant = (api.AccessToken(KEY, SECRET).with_identity('owner-' + uuid.uuid4().hex[:12]).with_name('owner')
             .with_grants(api.VideoGrants(room_join=True, room=room))
             .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=a) for a in (agents or [AGENT])])))
    return web.json_response({'server_url': SERVER_URL, 'participant_token': grant.to_jwt()})


def main():
    app = web.Application()
    app.router.add_post('/token', token)
    web.run_app(app, host=os.environ.get('LIVEKIT_LOCAL_BIND', '127.0.0.1'), port=int(os.environ.get('LIVEKIT_LOCAL_TOKEN_PORT', '7883')))


if __name__ == '__main__':
    main()
