# -*- coding: utf-8 -*-
"""会議の議事録の始めと終わりを、会話サーバーへ知らせる（minutes.py）。自宅サーバーで、会話サーバーのコンテナの中から使う。

  docker compose exec agent python minutes_admin.py rooms            シエルがいる部屋の一覧
  docker compose exec agent python minutes_admin.py start [部屋]     議事録をとり始める
  docker compose exec agent python minutes_admin.py finish [部屋]    議事録をまとめて、下書きを Discord へ送る

部屋を省くと、シエルがいる部屋が 1 つだけのときはそこへ送る。
LiveKit のサーバーの API（LIVEKIT_URL・LIVEKIT_API_KEY・LIVEKIT_API_SECRET）で、会話サーバーへだけ
データのメッセージ（topic ciel.minutes）を送る。アプリのボタンや声から送るときも、同じメッセージにする。
"""
import asyncio
import json
import sys

from livekit import api
from livekit.protocol import models, room

TOPIC = 'ciel.minutes'


async def agent_rooms(lk: api.LiveKitAPI) -> dict[str, str]:
    """シエル（会話サーバー）がいる部屋 → 会話サーバーの参加者の名前"""
    found = {}
    for r in (await lk.room.list_rooms(room.ListRoomsRequest())).rooms:
        for p in (await lk.room.list_participants(room.ListParticipantsRequest(room=r.name))).participants:
            if p.kind == models.ParticipantInfo.Kind.AGENT:
                found[r.name] = p.identity
    return found


async def main(args: list[str]) -> int:
    cmd = args[0] if args else ''
    if cmd not in ('rooms', 'start', 'finish') or len(args) > 2:
        print(__doc__)
        return 1
    async with api.LiveKitAPI() as lk:
        rooms = await agent_rooms(lk)
        if cmd == 'rooms':
            print('\n'.join(rooms) if rooms else 'シエルがいる部屋はありません')
            return 0
        if len(args) == 2:
            name = args[1]
            if name not in rooms:
                print(f'部屋 {name} にシエルはいません')
                return 1
        elif len(rooms) == 1:
            name = next(iter(rooms))
        else:
            print('シエルがいる部屋がありません' if not rooms else '部屋を指定してください：' + '、'.join(rooms))
            return 1
        data = json.dumps({'v': 1, 'type': 'minutes.control', 'action': cmd}).encode('utf-8')
        await lk.room.send_data(room.SendDataRequest(room=name, data=data, kind=models.DataPacket.Kind.RELIABLE,
                                                     topic=TOPIC, destination_identities=[rooms[name]]))
        print(f'{name} へ送りました：' + ('議事録をとり始めます' if cmd == 'start' else '議事録をまとめて、下書きを送ります'))
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv[1:])))
