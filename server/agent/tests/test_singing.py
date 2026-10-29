import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest

import numpy as np

import singing
from tools.singing import start_listening_to_song

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'singing'))
import analysis  # noqa: E402  歌を聴くサービス（server/singing）の、モデルを使わない部分


def melody(notes, hop=analysis.HOP, seed=0):
    """(MIDI, 秒, 種類) の並びから、音の高さの列（Hz）と周期のはっきりさを作る。0 は無音"""
    rng = np.random.default_rng(seed)
    f0, per = [], []
    for midi, seconds, kind in notes:
        n = int(seconds / hop)
        t = np.arange(n) * hop
        if midi == 0:
            f0.append(np.zeros(n))
            per.append(np.zeros(n))
            continue
        c = np.full(n, midi * 100.0)
        if kind == 'scoop':
            c -= 150 * np.clip(1 - t / 0.1, 0, 1)
        if kind == 'vib':
            c += 35 * np.sin(2 * np.pi * 5.5 * t)
        if kind == 'wobble':
            c += 45 * np.sin(2 * np.pi * 1.3 * t) + rng.normal(0, 8, n)
        if kind == 'off':
            c += 45
        f0.append(440 * 2 ** ((c / 100 - 69) / 12))
        per.append(np.ones(n))
    return np.concatenate(f0), np.concatenate(per)


class AnalysisTests(unittest.TestCase):
    def notes(self, f0, per):
        cents = analysis.to_cents(np.where(per >= analysis.PERIODICITY, f0, 0.0))
        return [analysis.describe_note(cents, a, b) for a, b in analysis.split_notes(cents)]

    def test_habits_are_found_and_counted_as_individuality(self):
        f0, per = melody([(67, .5, 'scoop'), (69, .5, ''), (71, 1.2, 'vib'), (0, .3, ''), (72, .5, 'scoop'),
                          (71, .5, ''), (69, 1.4, 'vib'), (0, .3, '')] * 3)
        notes = self.notes(f0, per)
        self.assertEqual(len(notes), 18)
        self.assertEqual(sum(n.scoop for n in notes), 6)
        self.assertEqual(sum(n.vibrato is not None for n in notes), 6)
        rate = np.mean([n.vibrato[0] for n in notes if n.vibrato])
        self.assertAlmostEqual(rate, 5.5, delta=0.6)
        audio = np.zeros(int(len(f0) * analysis.HOP * analysis.SR), np.float32)
        result = analysis.analyze(audio, f0, per, [], np.zeros((0, 768)), [(0.0, len(f0) * analysis.HOP)])
        self.assertIn('しゃくり', result['pitch']['habits'])
        self.assertIn('ビブラート', result['pitch']['habits'])
        self.assertEqual(result['pitch']['wobbles'], [])
        self.assertEqual(result['pitch']['off'], [])

    def test_wobble_and_off_note_are_only_suggestions(self):
        f0, per = melody([(67, .6, ''), (69, .6, ''), (71, .6, ''), (72, 1.5, 'wobble'), (0, .3, ''),
                          (74, .6, ''), (76, .6, 'off'), (74, .6, ''), (71, .6, ''), (67, 1.0, '')])
        notes = self.notes(f0, per)
        self.assertEqual([round(n.start, 1) for n in notes if n.wobble], [1.8])
        key, tuning, scale = analysis.estimate_key(notes)
        self.assertTrue(key.startswith('G'))
        self.assertEqual([round(n.start, 1) for n in analysis.off_notes(notes, tuning, scale)], [4.2])

    def test_flat_singer_is_judged_by_their_own_tuning(self):
        # いつも 30 セント低く歌う人：基準がずれているだけなので、外れたとは言わない
        f0, per = melody([(m - 0.3, .6, '') for m in (67, 69, 71, 72, 74, 72, 71, 69, 67)])
        notes = self.notes(f0, per)
        _, tuning, scale = analysis.estimate_key(notes)
        self.assertAlmostEqual(tuning, -30, delta=3)
        self.assertEqual(analysis.off_notes(notes, tuning, scale), [])

    def test_moments_prefer_overlapping_reasons(self):
        spans = analysis.windows(40.0)
        self.assertEqual(spans[0], (0.0, 10.0))
        aes = [{'CE': v, 'PQ': 7.0} for v in (4.0, 4.2, 5.5, 4.1, 4.0, 4.3, 3.9)]
        found = analysis.moments(aes, spans, builds=[10.0], changes=[10.0, 25.0])
        self.assertEqual(found[0]['start'], 10.0)
        self.assertEqual(found[0]['why'], ['響いた', '盛り上がり', '展開の変化'])
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(found, found[1:])))

    def test_changes_find_new_section(self):
        spans = analysis.windows(40.0)
        emb = np.ones((len(spans), 8))
        emb[3:, :4] = -1
        self.assertEqual(analysis.changes(emb, spans), [spans[3][0]])


LIVE = {'voiced': 0.8, 'band_db': -10.0, 'notes': 10, 'scoops': 0, 'vibratos': 0, 'wobbles': 0, 'ce': 4.5,
        'embedding': [1.0, 0.0]}

RESULT = {'tokimeki': {'score': 81, 'parts': [{'name': '響き', 'value': 20, 'max': 25}]},
          'duration': 95.0, 'sung_seconds': 80.0, 'offset': 0.4,
          'aesthetics': {'ce_mean': 4.8, 'ce_max': 6.1, 'ce_min': 3.9, 'pq_mean': 7.0,
                         'windows': [{'start': 0.0, 'end': 10.0, 'ce': 3.9}, {'start': 60.0, 'end': 70.0, 'ce': 6.1}]},
          'moments': [{'start': 60.0, 'end': 70.0, 'ce': 6.1, 'why': ['響いた', '盛り上がり']}],
          'builds': [60.0], 'changes': [], 'dynamics_db': 19.2,
          'voice': {'attack': 'soft', 'attack_ms': 140, 'brightness_hz': 900, 'breath_ratio': 0.004},
          'pitch': {'notes': 60, 'range': ['A3', 'E5'], 'key': 'G メジャー', 'tuning_cents': -12, 'long_notes': 9,
                    'vibrato': {'count': 4, 'rate_hz': 5.8, 'depth_cents': 30}, 'scoop_ratio': 0.42,
                    'fall_ratio': 0.05, 'habits': ['しゃくり', 'ビブラート'], 'wobbles': [72.4], 'off': [],
                    'off_ratio': 0.0}}


class LiveTests(unittest.TestCase):
    def test_meter_fills_then_heart_and_starts_over(self):
        # 心に響いた度をそのまま出すと満タンにならず、♡ が見られなかった（2026-10-29）。溜まったら ♡、0 から溜め直す
        cues = singing.LiveCues()
        base = {'band_db': -10.0, 'scoops': 0, 'vibratos': 0}
        self.assertIsNone(cues.update({'voiced': 0.1}, 5))   # 声がほとんど無い所
        events = [cues.update({**base, 'ce': 4.2, 'embedding': [1, 0]}, t) for t in (5, 10, 15)]
        self.assertEqual([e['meter'] for e in events], [0.165, 0.33, 0.495])   # 0.06 ＋ 0.35 × 0.3
        self.assertFalse(any(e['heart'] for e in events))
        # いちばん響いた・盛り上がりのおまけで満タン → ♡、0 に戻る
        e = cues.update({**base, 'ce': 5.0, 'band_db': -5.0, 'embedding': [1, 0]}, 20)
        self.assertTrue(e['heart'])
        self.assertEqual((e['meter'], e['hearts']), (0.0, 1))
        self.assertIn(e['comment'], singing.COMMENTS['peak'])
        self.assertEqual(e['expression'], 'excited')
        # 展開の変化とビブラートのおまけ。12 秒あかないうちは、ひとことを出さない
        e = cues.update({**base, 'ce': 4.0, 'vibratos': 1, 'embedding': [0, 1]}, 25)
        self.assertEqual((e['meter'], e['heart'], e['comment'], e['expression']), (0.397, False, '', ''))
        e = cues.update({**base, 'ce': 4.0, 'vibratos': 1, 'embedding': [0, 1]}, 35)
        self.assertIn(e['comment'], singing.COMMENTS['vibrato'])
        self.assertEqual(e['expression'], 'relaxed')

    def test_same_features_are_not_a_change(self):
        # 同じ特徴でも計算の誤差で違いが 0 より少し大きくなり、毎回「展開の変化」になっていた
        cues = singing.LiveCues()
        meters = [cues.update({'ce': 4.0, 'band_db': -10.0, 'embedding': [0.3, 0.7]}, t)['meter'] for t in range(5, 45, 5)]
        self.assertEqual(cues.hearts, 1)   # 0.1475 ずつ：7 回目で満タン
        self.assertLess(meters[-1], 0.2)
        self.assertIn('♡ 1 回', cues.summary())

    def test_result_card(self):
        card = singing.result_card(RESULT)
        self.assertEqual(card['moments'][0]['why'], '響いた・盛り上がり')
        self.assertEqual(card['habits'], 'しゃくり・ビブラート')
        self.assertEqual((card['hint_kind'], card['hint_at']), ('wobble', 72.4))
        self.assertEqual(singing.result_card({'duration': 5})['hint_at'], -1)

    def test_tokimeki_is_subjective_points(self):
        r = dict(RESULT, tokimeki=None)
        r['aesthetics'] = dict(RESULT['aesthetics'], ce_max=6.1)
        t = analysis.tokimeki(r)
        self.assertEqual([p['name'] for p in t['parts']], ['響き', 'ぐっときた瞬間', '表現', '伸び'])
        self.assertTrue(analysis.TOKIMEKI_BASE <= t['score'] <= 100)
        low = analysis.tokimeki({'moments': [], 'dynamics_db': 5})
        self.assertEqual(low['score'], analysis.TOKIMEKI_BASE + 4)   # 手がかりが無くても、聴かせてくれた点と伸びの半分


class FactsTests(unittest.TestCase):
    def test_facts_read_as_listening_cues(self):
        text = singing.facts(RESULT)
        self.assertIn('1分00秒〜1分10秒（響いた・盛り上がり）', text)
        self.assertIn('しゃくり（下から入る。音の 42%）', text)
        self.assertIn('揺れた伸ばす音：1分12秒', text)
        self.assertIn('強弱の幅：広い', text)
        self.assertIn('声の入り：柔らかい', text)
        self.assertNotIn('外れて聞こえた', text)   # 無ければ書かない
        self.assertNotIn('調', text)   # 調の名前は感想に使わない

    def test_feedback_prompt_has_facts_slot(self):
        import persona
        p = persona.load_persona()
        self.assertIn('{facts}', p.singing_feedback)
        self.assertIn('start_listening_to_song', p.singing_voice_instructions)


class Done:
    """generate_reply の戻り（待つとすぐ終わる）"""
    def __await__(self):
        return iter(())


class FakeSession:
    def __init__(self):
        self.replies = []
        self.audio = []
        self.input = Obj(set_audio_enabled=self.audio.append)

    def generate_reply(self, instructions, tool_choice=None):
        self.replies.append(instructions)
        return Done()


class FakeResponse:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class FakeHttp:
    def __init__(self, data):
        self.data, self.bodies, self.urls, self.lives = data, [], [], []

    def post(self, url, data=None, headers=None, timeout=None):
        self.urls.append(url)
        if url == singing.TTS_RELEASE_URL:
            return FakeResponse({'reserved_after_mib': 3000})
        if url == singing.LIVE_URL:
            self.lives.append(len(data))
            return FakeResponse(LIVE)
        self.bodies.append((data, headers))
        return FakeResponse(self.data)

    async def close(self):
        pass


class ListenerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = FakeSession()
        self.tap = Obj(listeners=[])
        self.events = []
        self.song = singing.SongListener(self.session, self.tap, '感想を言う\n{facts}')
        self.song.publish = self.events.append
        self.song._http = FakeHttp(RESULT)

    async def feed(self, seconds, level=0.1):
        t = self.song._ready_at + 0.01
        for i in range(int(seconds * 100)):
            pcm = (np.sin(np.arange(160) / 3) * level * 32767).astype(np.int16)
            for listener in list(self.tap.listeners):
                listener(t + i * 0.01, pcm)

    async def ready(self):
        for _ in range(50):
            if self.song._ready_at is not None:
                return
            await asyncio.sleep(0.01)
        self.fail('「どうぞ」が終わらない')

    async def test_song_is_kept_local_and_feedback_gets_only_text(self):
        self.assertEqual(self.song.start(), singing.STARTED)
        self.assertEqual(self.session.audio, [False])   # 会話モデルへの声を止めた
        await self.ready()
        self.assertEqual(self.session.replies, [singing.LINES[singing.STARTED]])
        await self.feed(4.0)
        self.song.finish()
        await self.song._task
        self.assertEqual(self.session.audio, [False, True])
        self.assertEqual(self.tap.listeners, [])
        # 読み上げのメモリーを、歌い始め（歌の途中の分析のため）と分析の前に手放す
        self.assertEqual(self.song._http.urls, [singing.TTS_RELEASE_URL, singing.TTS_RELEASE_URL, singing.URL])
        body, headers = self.song._http.bodies[0]
        self.assertEqual(len(body), 400 * 160 * 2)
        self.assertEqual(headers['X-Sample-Rate'], '16000')
        self.assertTrue(self.session.replies[-1].startswith('感想を言う\n聴き取りの手がかり'))
        self.assertEqual([e['state'] for e in self.events if e['type'] == 'song.state'], ['listening', 'analyzing', 'idle'])
        card = [e for e in self.events if e['type'] == 'song.result'][0]
        self.assertEqual(card['score'], 81)
        self.assertEqual(card['hint_kind'], 'wobble')
        self.assertIn('ときめき度', self.session.replies[-1])
        self.assertEqual(self.song._chunks, [])

    async def test_live_cues_are_sent_while_singing(self):
        old = singing.LIVE_EVERY
        singing.LIVE_EVERY = 0.2
        try:
            self.song.start()
            await self.ready()
            await self.feed(4.0)
            for _ in range(20):
                await asyncio.sleep(0.05)
                if any(e['type'] == 'song.live' for e in self.events):
                    break
            self.assertTrue(self.song._http.lives)
            self.assertLessEqual(self.song._http.lives[0], int(singing.LIVE_WINDOW * 16000) * 2 + 320)
            live = [e for e in self.events if e['type'] == 'song.live']
            self.assertEqual(live[0]['meter'], 0.191)   # 0.06 ＋ 0.35 × 0.375
            self.assertEqual(self.session.replies, [singing.LINES[singing.STARTED]])   # 歌の途中は話さない
            self.song.cancel()
        finally:
            singing.LIVE_EVERY = old

    async def test_quiet_until_feedback_is_spoken_then_old_thoughts_dropped(self):
        # 歌の前の考え（「これから歌ってくれる」）を、歌のあとで話していた（2026-10-27）
        ended = []
        self.song.on_end = lambda: ended.append(self.song.active)
        self.song.start()
        await self.ready()
        await self.feed(4.0)
        speaking = asyncio.get_running_loop().create_future()
        replies = []

        def reply(instructions, tool_choice=None):
            replies.append(instructions)
            return speaking
        self.session.generate_reply = reply
        self.song.finish()
        self.assertEqual(self.session.audio, [False])   # 分析中は、まだ会話モデルへ声を送らない
        for _ in range(20):
            await asyncio.sleep(0.01)
            if replies:
                break
        self.assertEqual(self.session.audio, [False, True])   # 感想を話し始めるときに戻す
        self.assertTrue(replies[0].startswith('感想を言う'))
        self.assertEqual(self.song.state, singing.IDLE)   # アプリには終わったと見せる
        self.assertTrue(self.song.active)                 # 感想を話し終えるまで、シエルから話しかけない
        self.assertEqual(ended, [])
        speaking.set_result(None)
        await self.song._task
        self.assertFalse(self.song.active)
        self.assertEqual(ended, [False])

    async def test_song_end_is_written_into_the_conversation_first(self):
        # 会話の最後が「どうぞ」のままだと、結果が出たあとに「歌い始めた」ような返事をした（2026-10-29）
        order = []

        class Ctx:
            def __init__(self, items=()):
                self.items = list(items)

            def copy(self):
                return Ctx(self.items)

            def add_message(self, role, content):
                item = Obj(id=f'item{len(self.items)}', role=role, content=content)
                self.items.append(item)
                return item

        class Agent:
            chat_ctx = Ctx()
            realtime_llm_session = Obj(chat_ctx=Ctx())

            async def update_chat_ctx(self, ctx):
                order.append(('note', ctx.items[-1].role, ctx.items[-1].content))
                Agent.chat_ctx = ctx

        self.session.current_agent = Agent()
        reply = self.session.generate_reply

        def generate(instructions, tool_choice=None):
            order.append(('reply', instructions[:5]))
            return reply(instructions, tool_choice)
        self.session.generate_reply = generate
        self.song.start()
        await self.ready()
        await self.feed(4.0)
        self.song.finish()
        await self.song._task
        note, answer = order[-2], order[-1]
        self.assertEqual(note[:2], ('note', 'system'))
        self.assertTrue(note[2].startswith('[歌：相手が歌い終えた。シエルは最後まで聴いた（1分35秒）'))
        self.assertIn('ときめき度', note[2])
        self.assertNotIn('話す順番', note[2])   # 感想の言い方の指示は会話に残さない
        self.assertEqual(answer, ('reply', '感想を言う'))

    async def test_douzo_is_cut_after_two_sentences(self):
        requested = []
        self.song.preamble = Obj(request=lambda speech, keep: requested.append(keep))
        self.song.start()
        await self.ready()
        self.assertEqual(requested, [singing.DOUZO_SENTENCES])
        self.song.cancel()
        await self.song._task

    async def test_short_song_is_not_sent(self):
        self.song.start()
        await self.ready()
        await self.feed(1.0)
        self.song.finish()
        await self.song._task
        self.assertEqual(self.song._http.bodies, [])
        self.assertEqual(self.session.replies[-1], singing.LINES[singing.EMPTY])
        self.assertEqual(self.song.state, singing.IDLE)

    async def test_silence_after_singing_finishes(self):
        old = singing.SILENCE_END
        singing.SILENCE_END = 0.3
        try:
            self.song.start()
            await self.ready()
            await self.feed(4.0)
            for _ in range(40):
                await asyncio.sleep(0.05)
                if self.song.state == singing.IDLE:
                    break
            self.assertEqual(len(self.song._http.bodies), 1)
        finally:
            singing.SILENCE_END = old

    async def test_cancel_and_app_message(self):
        self.song.on_data(Obj(topic='ciel.song', data=json.dumps({'action': 'start'}).encode()))
        await self.ready()
        self.assertEqual(self.song.start(), singing.ALREADY)
        self.song.on_data(Obj(topic='ciel.song', data=json.dumps({'action': 'cancel'}).encode()))
        self.assertEqual(self.song.state, singing.IDLE)
        await self.song._task
        self.assertEqual(self.session.audio, [False, True])
        self.assertEqual(self.session.replies[-1], singing.LINES[singing.CANCELLED])

    async def test_service_failure_is_told(self):
        class Broken(FakeHttp):
            def post(self, *a, **k):
                raise ConnectionError
        self.song._http = Broken(None)
        self.song.start()
        await self.ready()
        await self.feed(4.0)
        self.song.finish()
        await self.song._task
        self.assertEqual(self.session.replies[-1], singing.LINES[singing.FAILED])
        self.assertEqual(self.song.state, singing.IDLE)

    async def test_tool_starts_without_reply(self):
        context = Obj(userdata=Obj(song=self.song))
        result = await start_listening_to_song(context)
        self.assertEqual(json.loads(result.output)['status'], singing.STARTED)
        self.assertFalse(result.reply_required)
        await self.song.close()


if __name__ == '__main__':
    unittest.main()
