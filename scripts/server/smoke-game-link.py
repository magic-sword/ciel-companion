#!/usr/bin/env python3
"""Verify a conversation can bind game inference and observe a connected body.

Run in the deployed agent container. No game actions are submitted. The shared
body must be released by the user's conversation before running this check.
"""
import argparse
import asyncio
import json
import os
import uuid

from livekit import api, rtc


async def run(agent):
    lk, room = api.LiveKitAPI(), rtc.Room()
    name = 'game-link-smoke-' + uuid.uuid4().hex[:12]
    ready, linked = asyncio.Event(), asyncio.Event()
    state = {}

    @room.on('data_received')
    def event(packet):
        nonlocal state
        if packet.topic != 'ciel.event':
            return
        try:
            value = json.loads(packet.data)
        except (ValueError, UnicodeError):
            return
        if value.get('type') == 'voice.ready' and value.get('ready'):
            ready.set()
        if value.get('type') == 'env.state' and value.get('game') == 'minecraft':
            state = value
            if value.get('linked') and value.get('playing') or value.get('reason') == 'busy':
                linked.set()

    async def link(on):
        await room.local_participant.publish_data(json.dumps({
            'v': 1, 'type': 'env.link', 'game': 'minecraft', 'on': on}),
            reliable=True, topic='ciel.game')

    try:
        await lk.room.create_room(api.CreateRoomRequest(name=name,
            agents=[api.RoomAgentDispatch(agent_name=agent)]))
        token = api.AccessToken().with_identity('game-link-smoke-user').with_grants(
            api.VideoGrants(room_join=True, room=name)).to_jwt()
        await room.connect(os.environ['LIVEKIT_URL'], token)
        await room.local_participant.publish_data(json.dumps({'v': 1, 'type': 'voice.ready_request'}),
            reliable=True, topic='ciel.event')
        await asyncio.wait_for(ready.wait(), 180)
        await link(True)
        await asyncio.wait_for(linked.wait(), 100)
        if not state.get('linked') or not state.get('playing'):
            raise RuntimeError('game_link_failed:' + str(state.get('reason')))
        return {'status': 'passed', 'agent': agent, 'linked': True, 'playing': True,
                'scope': 'Game connection and inference binding; no world actions submitted'}
    finally:
        try:
            if room.isconnected():
                await link(False)
        finally:
            await room.disconnect()
            try:
                await lk.room.delete_room(api.DeleteRoomRequest(room=name))
            finally:
                await lk.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True)
    print(json.dumps(asyncio.run(run(parser.parse_args().agent))))
