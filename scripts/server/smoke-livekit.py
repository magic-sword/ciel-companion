#!/usr/bin/env python3
"""Deployment smoke: readiness, greeting, text input and reply audio in a temporary room.

Run in an agent image with its existing LiveKit environment. Default dispatch is
explicitly selected for an unnamed production worker; this is not a voice benchmark.
"""
import argparse
import asyncio
import audioop
import json
import os
import time
import uuid

from livekit import api, rtc


async def run(args):
    lk=api.LiveKitAPI()
    room=rtc.Room()
    name='deploy-smoke-'+uuid.uuid4().hex[:12]
    identity='deploy-smoke-user'
    ready=asyncio.Event();greeting=asyncio.Event();reply=asyncio.Event()
    tasks=[];last_loud=0.0;request_at=None;ready_info=None

    @room.on('data_received')
    def event(packet):
        nonlocal ready_info
        if packet.topic!='ciel.event':return
        try:value=json.loads(packet.data)
        except (ValueError,UnicodeError):return
        if value.get('type')=='voice.ready' and value.get('ready') is True:
            ready_info=value;ready.set()

    async def listen(track):
        nonlocal last_loud
        async for frame in rtc.AudioStream(track,sample_rate=16000,num_channels=1):
            if audioop.rms(frame.frame.data.tobytes(),2)/32768>.01:
                last_loud=time.monotonic();greeting.set()
                if request_at is not None:reply.set()

    @room.on('track_subscribed')
    def subscribed(track,publication,participant):
        if track.kind==rtc.TrackKind.KIND_AUDIO and publication.name!='ciel-aizuchi':
            tasks.append(asyncio.create_task(listen(track)))

    started=time.monotonic()
    try:
        kwargs={} if args.default_agent else {'agents':[api.RoomAgentDispatch(agent_name=args.agent)]}
        await lk.room.create_room(api.CreateRoomRequest(name=name,**kwargs))
        token=(api.AccessToken().with_identity(identity).with_grants(api.VideoGrants(room_join=True,room=name)).to_jwt())
        await room.connect(os.environ['LIVEKIT_URL'],token)
        await room.local_participant.publish_data(json.dumps({'v':1,'type':'voice.ready_request'}),reliable=True,topic='ciel.event')
        await asyncio.wait_for(ready.wait(),180)
        await asyncio.wait_for(greeting.wait(),90)
        deadline=time.monotonic()+90
        while time.monotonic()-last_loud<2.5:
            if time.monotonic()>deadline:raise TimeoutError('Greeting did not settle')
            await asyncio.sleep(.1)
        request_at=time.monotonic()
        await room.local_participant.send_text('こんにちは、シエル。',topic='lk.chat')
        await asyncio.wait_for(reply.wait(),60)
        return {'status':'passed','scope':'Deployment connectivity only; text input to reply audio',
                'readiness':ready_info.get('ready'),'greeting_audio':True,'reply_audio':True,
                'reply_ms':round((time.monotonic()-request_at)*1000,2),
                'total_seconds':round(time.monotonic()-started,3)}
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await room.disconnect()
        try:await lk.room.delete_room(api.DeleteRoomRequest(room=name))
        finally:await lk.aclose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--agent')
    group.add_argument('--default-agent',action='store_true')
    args=parser.parse_args()
    print(json.dumps(asyncio.run(run(args))))
