"""見せてもらった画像（eyes.py）と、心への添え方（mind.py）"""
import asyncio
import types
import unittest
from unittest import mock

from livekit.agents import llm

import eyes
import mind
from conversation import Conversation

JPEG = b'\xff\xd8\xff\xe0' + b'0' * 100
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 100


class Said:
    def __init__(self):
        self.calls = []

    def __call__(self, why, **kwargs):
        self.calls.append((why, kwargs))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def ctx_with(text):
    ctx = llm.ChatContext()
    ctx.add_message(role='system', content='会話の指示')
    if text is not None:
        ctx.add_message(role='user', content=text)
    return ctx


class EyesTest(unittest.TestCase):
    def setUp(self):
        self.said, self.shown, self.clock = Said(), [], Clock()
        self.eyes = eyes.Eyes(self.said, notify=self.shown.append, clock=self.clock)

    def test_kind_comes_from_the_bytes(self):
        self.assertEqual(eyes.mime_of(JPEG), 'image/jpeg')
        self.assertEqual(eyes.mime_of(PNG), 'image/png')
        self.assertEqual(eyes.mime_of(b'RIFF0000WEBPxxxx'), 'image/webp')
        self.assertIsNone(eyes.mime_of(b'RIFF0000WAVEfmt '))
        self.assertIsNone(eyes.mime_of(b'<svg>'))

    def test_a_picture_is_kept_and_ciel_is_asked_to_look(self):
        pic = self.eyes.receive(JPEG, 'cat.jpg')
        self.assertTrue(pic.data_url.startswith('data:image/jpeg;base64,'))
        self.assertEqual(self.shown[-1], {'v': 1, 'type': 'image.state', 'state': 'received', 'id': 1})
        self.assertEqual(self.said.calls[0][0], 'image')

    def test_not_an_image_is_refused(self):
        self.assertIsNone(self.eyes.receive(b'hello', 'a.txt'))
        self.assertEqual(self.shown[-1]['reason'], 'not_image')
        self.assertEqual(self.said.calls, [])

    def test_only_the_last_few_are_kept(self):
        for _ in range(5):
            self.eyes.receive(JPEG)
        self.assertEqual([p.id for p in self.eyes.pictures], [3, 4, 5])

    def test_the_picture_goes_with_one_reply_then_only_when_pointed_at(self):
        self.eyes.receive(JPEG, 'cat.jpg')
        self.assertTrue(self.eyes.wants('これどう？'))
        msg = self.eyes.message_for_reply('これどう？')
        self.assertIsInstance(msg.content[1], llm.ImageContent)
        self.assertIn('#1（cat.jpg）', msg.content[0])
        # 見たら、ふつうの話では添えない。画像を指したら、もう一度
        self.assertFalse(self.eyes.wants('今日は暑いね'))
        self.assertTrue(self.eyes.wants('さっきの絵の右の子は？'))
        # 時間がたったら、指しても添えない
        self.clock.now += eyes.RECALL_SECONDS + 1
        self.assertFalse(self.eyes.wants('さっきの絵の右の子は？'))

    def test_captions_are_shown_as_text(self):
        self.assertIsNone(self.eyes.context())
        pic = self.eyes.receive(JPEG)
        pic.caption = '白い犬の耳の女の子のイラスト'
        self.clock.now += 125
        self.assertEqual(self.eyes.context(), '[見せてもらった画像]\n#1（2 分前）：白い犬の耳の女の子のイラスト')


class SourceTest(unittest.TestCase):
    def test_views_and_shown_pictures_are_kept_apart(self):
        said = Said()
        e = eyes.Eyes(said)
        shown = e.receive(JPEG, 'cat.jpg')
        for _ in range(4):
            view = e.see_game(JPEG, '北を向いている', 'マイクラ')
        # 景色を何枚見ても、見せてもらった画像は押し出されない
        self.assertIn(shown, e.pictures)
        self.assertEqual(len([p for p in e.pictures if p.source == eyes.GAME]), eyes.KEEP)
        self.assertEqual(len(said.calls), 1)   # 口に頼むのは、見せてもらった画像だけ
        # 新しいものから見る。前の景色は、見ていなくても、もう添えない
        self.assertIn('[わたしの目に見えている景色 #5（マイクラの中で、今わたしが見ているもの。北を向いている）]',
                      e.message_for_reply('何が見える？').content[0])
        self.assertIn('[見せてもらった画像 #1', e.message_for_reply('').content[0])
        self.assertIsNone(e.message_for_reply(''))
        shown.caption, view.caption = '猫の写真', '川と森の景色'
        ctx = e.context()
        self.assertIn('[見せてもらった画像]\n#1', ctx)
        self.assertIn('[わたしの目で見た景色（マイクラ）]\n#5', ctx)

    def test_not_an_image_view_is_dropped(self):
        self.assertIsNone(eyes.Eyes(Said()).see_game(b'nope'))


class Reader:
    def __init__(self, chunks, name='x.jpg'):
        self.chunks, self.info = chunks, types.SimpleNamespace(name=name)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self.chunks:
            yield c


class StreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_is_read_and_too_large_is_refused(self):
        shown = []
        e = eyes.Eyes(Said(), notify=shown.append)
        await e._receive(Reader([JPEG[:3], JPEG[3:]]))
        self.assertEqual(shown[-1]['state'], 'received')
        with mock.patch.object(eyes, 'MAX_BYTES', 50):
            await e._receive(Reader([JPEG]))
        self.assertEqual(shown[-1], {'v': 1, 'type': 'image.state', 'state': 'failed', 'reason': 'too_large'})


class MindTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_unseen_picture_goes_to_the_mind_and_only_the_mind_sees_it(self):
        e = eyes.Eyes(Said())
        m = mind.Mind(Conversation(), eyes=e)
        e.receive(JPEG)
        ctx = ctx_with('これどう？')
        self.assertEqual(m.route(ctx, {'seconds': 1.0}), 'mind')
        talker = m.build(ctx, talker_instructions='短い指示', turn={})
        self.assertFalse(any(isinstance(c, llm.ImageContent) for i in talker.items for c in getattr(i, 'content', [])))
        deep = m.build(ctx, turn={})
        self.assertTrue(any(isinstance(c, llm.ImageContent) for i in deep.items for c in getattr(i, 'content', [])))
        self.assertEqual(m.route(ctx_with('ありがとう'), {'seconds': 1.0}), 'talker')

    def test_ciels_own_picture_always_follows_the_instructions(self):
        m = mind.Mind(Conversation(), self_image='data:image/jpeg;base64,AAAA')
        ctx = ctx_with('こんにちは')
        for built in (m.build(ctx, turn={}), m.build(ctx, talker_instructions='短い指示', turn={})):
            first = built.items[1]
            self.assertEqual(built.items[0].role, 'system')
            self.assertIn('[わたしの姿]', first.content[0])
            self.assertIsInstance(first.content[1], llm.ImageContent)

    def test_the_notice_alone_shows_the_picture(self):
        e = eyes.Eyes(Said())
        m = mind.Mind(Conversation(), eyes=e)
        e.receive(PNG)
        m.on_say('image')
        ctx = ctx_with(None)
        self.assertEqual(m.route(ctx), 'mind')
        self.assertTrue(any(isinstance(c, llm.ImageContent) for i in m.build(ctx).items for c in getattr(i, 'content', [])))


class LocalVisionTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_images_and_game_views_require_confirmed_capability(self):
        with mock.patch('models.is_local', return_value=True):
            e = eyes.Eyes(Said())
        self.assertIsNone(e.receive(JPEG))
        with mock.patch('models.vision_available', mock.AsyncMock(return_value=True)):
            await e.prepare()
        self.assertIsNotNone(e.receive(JPEG))
        self.assertIsNotNone(e.see_game(PNG, place='test'))
        self.assertIsInstance(e.message_for_reply('').content[1], llm.ImageContent)

    async def test_unavailable_local_api_does_not_keep_or_infer_an_image(self):
        shown = []
        with mock.patch('models.is_local', return_value=True):
            e = eyes.Eyes(Said(), notify=shown.append)
        with mock.patch('models.vision_available', mock.AsyncMock(return_value=False)):
            await e._receive(Reader([JPEG]))
        self.assertFalse(e.pictures)
        self.assertEqual(shown[-1]['reason'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
