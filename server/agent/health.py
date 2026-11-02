# -*- coding: utf-8 -*-
"""会話サーバーの不調をアプリへ知らせる（topic ciel.event の agent.problem）。

OpenAI の残高が切れたとき、聞き取り（STT）と返事（LLM）が失敗して会話が止まったのに、アプリは「つながっています」の
ままで、シエルが反応しない理由が分からなかった（2026-11-02）。LiveKit の会話（AgentSession）の error・close を見て、
何が使えないかをアプリの接続の表示に出してもらう。

- kind：quota（残高切れ）・auth（API キーが使えない）・rate_limit（混んでいる）・error（そのほか）。
- service：stt（聞き取り）・llm（返事）・tts（読み上げ）・other。
- stopped：会話が止まった（close の理由が error）。止まっていなければ、アプリはしばらくして表示を戻す。
- 同じ不調は続けて送らない（聞き取りは失敗するたびに作り直されて、何度も error が来る）。止まったときは必ず送る。
- 相手に見せる文はアプリが決める。ここではエラーの本文（API の返事）を送らない・ログに出さない（中身に何が入るか分からない）。
"""
import logging

log = logging.getLogger('ciel-agent.health')

QUOTA_MARKS = ('insufficient_quota', 'credit_balance_exhausted', 'no credits remaining', 'exceeded your current quota')
AUTH_MARKS = ('invalid_api_key', 'incorrect api key')


def classify(error) -> str:
    """失敗の中身（LiveKit の LLMError・STTError など、または例外）から、不調の種類を決める"""
    inner = getattr(error, 'error', error)
    text = f'{inner} {getattr(inner, "body", "")}'.lower()
    status = getattr(inner, 'status_code', None)
    if any(m in text for m in QUOTA_MARKS):
        return 'quota'
    if status in (401, 403) or any(m in text for m in AUTH_MARKS):
        return 'auth'
    if status == 429 or 'rate limit' in text:
        return 'rate_limit'
    return 'error'


def service(error) -> str:
    """失敗した係（LiveKit のエラーの type：llm_error・stt_error・tts_error）"""
    kind = getattr(error, 'type', '') or ''
    for name in ('stt', 'llm', 'tts'):
        if kind.startswith(name):
            return name
    return 'other'


class Health:
    def __init__(self, publish) -> None:
        self.publish = publish   # アプリへの知らせ（agent.py の notify）
        self._last: tuple[str, str] | None = None
        self.stopped = False

    def on_error(self, ev) -> None:
        """AgentSession の error。立て直せる失敗（recoverable）でも、同じ不調が続くなら知らせる"""
        error = getattr(ev, 'error', None)
        if error is None:
            return
        problem = (classify(error), service(error))
        if problem == self._last:
            return
        self._last = problem
        log.warning('不調：%s（%s）', *problem)
        self._tell(*problem, stopped=False)

    def on_close(self, ev) -> None:
        """AgentSession の close。エラーで止まったら、止まったことを知らせる"""
        if getattr(getattr(ev, 'reason', None), 'value', getattr(ev, 'reason', None)) != 'error':
            return
        error = getattr(ev, 'error', None)
        kind, svc = (classify(error), service(error)) if error is not None else (self._last or ('error', 'other'))
        self.stopped = True
        log.warning('会話が止まった：%s（%s）', kind, svc)
        self._tell(kind, svc, stopped=True)

    def _tell(self, kind: str, svc: str, stopped: bool) -> None:
        self.publish({'v': 1, 'type': 'agent.problem', 'kind': kind, 'service': svc, 'stopped': stopped})
