"""Semantic memory operations, independent of LiveKit and model tool schemas.

The host supplies its trusted speaker book and writer. No method accepts an actor ID.
SpeakerBook/Store retain ownership, consent and main/dev scope enforcement.
"""
NO_SPEAKERS = '今は話している人を区別していません。'


class MemoryService:
    def __init__(self, book, notes):
        self.book, self.notes = book, notes

    async def recall(self):
        return await self.book.recall() if self.book else NO_SPEAKERS

    async def agree(self):
        return await self.book.agree_notes() if self.book else NO_SPEAKERS

    async def remember(self, note):
        book = self.book
        if book is None or self.notes is None:
            return {'status': 'unavailable', 'message': NO_SPEAKERS}
        await book.refresh()
        person = book.current_person()
        if person is None:
            return {'status': 'unidentified', 'message': 'いま話している方を確かに識別できないので、覚えられません。'}
        if not person.notes_ok:
            return {'status': 'consent_required',
                    'message': f'{person.name}さんからは、お話を覚える同意をまだもらっていません。先に同意を聞いてください。'}
        if not note.strip() or len(note) > 2000:
            return {'status': 'invalid_note', 'message': '覚える内容を短い文で教えてください。'}
        self.notes.request(person.person_id, note)
        return {'status': 'queued', 'message': '保存を受け付けました（裏で保存します）。'}

    async def forget(self, what):
        book = self.book
        if book is None or self.notes is None:
            return NO_SPEAKERS
        await book.refresh()
        person = book.current_person()
        if person is None:
            return 'いま話している方を確かに識別できないので、受け付けられません。ご本人にもう一度言ってもらってください。'
        if not what.strip():
            return '忘れる内容を教えてください。'
        if book.store is not None and hasattr(book.store, 'request_forget'):
            if not await book.store.request_forget(person.person_id, what):
                return '保存されている本人情報を確認できませんでした。'
        self.notes.forget(person.person_id, what)
        # Suppress cached memories immediately, while the writer processes the request.
        book.last.memory_suppressed = True
        book.last.notes_context = ''
        book.last.relation_context.clear()
        return '忘れる処理を受け付けました。この会話でも、もうその話はしない。'
