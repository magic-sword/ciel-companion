"""ローカル試験用の文字入力端末。LiveKit の開発用会話サーバーへ接続する。

CIEL_DEV_LLM_BACKEND=local で agent-dev を起動してから python local_chat.py。
OpenAI は呼ばないが、接続先の会話サーバーの設定と LiveKit の利用料は別。
"""
import argparse
import asyncio
import json
import os
import uuid

from dotenv import load_dotenv
from livekit import api, rtc


async def chat(args):
    load_dotenv()
    room_name = 'local-test-' + uuid.uuid4().hex[:10]
    room = rtc.Room()
    ready, linked = asyncio.Event(), asyncio.Event()

    @room.on('data_received')
    def on_data(packet):
        try:
            msg = json.loads(packet.data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return
        if packet.topic == 'ciel.event' and msg.get('type') == 'env.list':
            ready.set()
        if packet.topic == 'ciel.event' and msg.get('type') == 'env.state':
            print('ゲーム:', msg.get('game'), msg.get('reason', ''), 'playing=', msg.get('playing'))
            if msg.get('playing'):
                linked.set()
        if packet.topic == 'ciel.goal':
            print('目的:', json.dumps(msg, ensure_ascii=False))

    async def read_transcription(reader):
        text = await reader.read_all()
        if text.strip():
            print('\nシエル:', text)

    tasks = set()

    def transcription(reader, identity):
        task = asyncio.create_task(read_transcription(reader))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler('lk.transcription', transcription)
    async with api.LiveKitAPI() as lk:
        try:
            await lk.room.create_room(api.CreateRoomRequest(
                name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
            token = (api.AccessToken().with_identity('local-test-user').with_name('試験用の文字入力')
                     .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
            await room.connect(os.environ['LIVEKIT_URL'], token)
            await asyncio.wait_for(ready.wait(), 90)
            if args.game:
                await room.local_participant.publish_data(
                    json.dumps({'v': 1, 'type': 'env.link', 'game': args.game, 'on': True}),
                    reliable=True, topic='ciel.game')
                await asyncio.wait_for(linked.wait(), 30)
            print('文字で指示を入力。/quit で終了。返答や操作の完了を待って次を入力してください。')
            while True:
                line = await asyncio.to_thread(input, '> ')
                if line.strip() == '/quit':
                    break
                if line.strip():
                    await room.local_participant.send_text(line, topic='lk.chat')
        finally:
            await room.disconnect()
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', default='ciel-dev')
    parser.add_argument('--game', default='', help='ゲームの識別名。省略ならゲームにつながない')
    try:
        asyncio.run(chat(parser.parse_args()))
    except (KeyboardInterrupt, EOFError):
        pass
