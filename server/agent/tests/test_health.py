import enum
import types
import unittest

import health


class Reason(enum.Enum):
    ERROR = 'error'
    PARTICIPANT_DISCONNECTED = 'participant_disconnected'


class StatusError(Exception):
    def __init__(self, message, status_code=-1, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def failure(kind, error):
    return types.SimpleNamespace(type=kind, error=error, recoverable=True)


QUOTA = StatusError("Error code: 429 - {'error': {'type': 'insufficient_quota', 'code': 'credit_balance_exhausted'}}",
                    status_code=429)


class ClassifyTest(unittest.TestCase):
    def test_quota_is_not_mistaken_for_a_rate_limit(self):
        self.assertEqual(health.classify(failure('llm_error', QUOTA)), 'quota')
        self.assertEqual(health.classify(Exception('You have no credits remaining. Add credits ...')), 'quota')

    def test_auth_rate_limit_and_other(self):
        self.assertEqual(health.classify(StatusError('bad key', status_code=401)), 'auth')
        self.assertEqual(health.classify(StatusError('slow down', status_code=429)), 'rate_limit')
        self.assertEqual(health.classify(RuntimeError('boom')), 'error')

    def test_service_from_the_error_type(self):
        self.assertEqual(health.service(failure('stt_error', QUOTA)), 'stt')
        self.assertEqual(health.service(failure('llm_error', QUOTA)), 'llm')
        self.assertEqual(health.service(failure('tts_error', QUOTA)), 'tts')
        self.assertEqual(health.service(RuntimeError('x')), 'other')


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.h = health.Health(self.sent.append)

    def test_repeated_problem_is_sent_once(self):
        for _ in range(3):
            self.h.on_error(types.SimpleNamespace(error=failure('stt_error', QUOTA)))
        self.h.on_error(types.SimpleNamespace(error=failure('llm_error', QUOTA)))
        self.assertEqual([(m['kind'], m['service'], m['stopped']) for m in self.sent],
                         [('quota', 'stt', False), ('quota', 'llm', False)])

    def test_close_by_error_says_stopped(self):
        self.h.on_close(types.SimpleNamespace(reason=Reason.ERROR, error=failure('stt_error', QUOTA)))
        self.assertEqual(self.sent, [{'v': 1, 'type': 'agent.problem', 'kind': 'quota', 'service': 'stt', 'stopped': True}])
        self.assertTrue(self.h.stopped)

    def test_close_without_error_uses_the_last_problem(self):
        self.h.on_error(types.SimpleNamespace(error=failure('llm_error', QUOTA)))
        self.h.on_close(types.SimpleNamespace(reason=Reason.ERROR, error=None))
        self.assertEqual(self.sent[-1]['stopped'], True)
        self.assertEqual((self.sent[-1]['kind'], self.sent[-1]['service']), ('quota', 'llm'))

    def test_normal_close_is_not_a_problem(self):
        self.h.on_close(types.SimpleNamespace(reason=Reason.PARTICIPANT_DISCONNECTED, error=None))
        self.assertEqual(self.sent, [])

    def test_error_body_is_not_forwarded(self):
        self.h.on_error(types.SimpleNamespace(error=failure('llm_error', QUOTA)))
        self.assertNotIn('credit', str(self.sent))


if __name__ == '__main__':
    unittest.main()
