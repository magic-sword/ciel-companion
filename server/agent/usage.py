# -*- coding: utf-8 -*-
"""会話モデルの使用量の記録：返事ごとの入力・出力のトークン数をログに出す（会話の中身は出さない）。

LiveKit は、会話モデルが返事を 1 つ終えるたびに、この会話の累計の使用量を知らせる（session_usage_updated）。
前の知らせとの差を、その返事の使用量としてログに出す。会話の終わりに累計も出す。
ログの例：「使用量 返事 入力 18,240（キャッシュ 17,920・98%、文字 15,100・音声 3,140） 出力 96」。
返事を頼んでから書き始めるまでの時間は、latency.py の「返事の速さ」（返事を頼んだ → 最初の文字）で見る。
"""
import logging

log = logging.getLogger('ciel-agent.usage')

FIELDS = ('input_tokens', 'input_cached_tokens', 'input_text_tokens', 'input_audio_tokens',
          'output_tokens', 'output_text_tokens', 'output_reasoning_tokens')


class UsageLog:
    def __init__(self) -> None:
        self._last: dict[tuple[str, str], dict[str, int]] = {}
        self.replies = 0

    def on_usage(self, ev) -> None:
        for u in ev.usage.model_usage:
            if getattr(u, 'type', None) != 'llm_usage':
                continue
            now = {f: int(getattr(u, f, 0) or 0) for f in FIELDS}
            before = self._last.get((u.provider, u.model), dict.fromkeys(FIELDS, 0))
            self._last[(u.provider, u.model)] = now
            d = {f: now[f] - before[f] for f in FIELDS}
            if d['input_tokens'] <= 0 and d['output_tokens'] <= 0:
                continue
            self.replies += 1
            log.info('使用量 返事 入力 %s（キャッシュ %s・%d%%、文字 %s・音声 %s） 出力 %s（文字 %s・考える %s）',
                     f"{d['input_tokens']:,}", f"{d['input_cached_tokens']:,}", percent(d), f"{d['input_text_tokens']:,}",
                     f"{d['input_audio_tokens']:,}", f"{d['output_tokens']:,}", f"{d['output_text_tokens']:,}",
                     f"{d['output_reasoning_tokens']:,}")

    def summary(self) -> None:
        """会話の終わりに、この会話の累計を出す"""
        for (provider, model), t in self._last.items():
            log.info('使用量 会話の累計 %s 返事 %d 回 入力 %s（キャッシュ %s・%d%%） 出力 %s',
                     model, self.replies, f"{t['input_tokens']:,}", f"{t['input_cached_tokens']:,}", percent(t),
                     f"{t['output_tokens']:,}")


def percent(t: dict[str, int]) -> int:
    return round(100 * t['input_cached_tokens'] / t['input_tokens']) if t['input_tokens'] else 0
