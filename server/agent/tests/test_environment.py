"""Environment migration must preserve settings without crossing production/dev scopes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('ciel_environment', Path(__file__).resolve().parents[2] / 'environment.py')
environment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(environment)

class EnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prod = Path(self.temp.name) / 'prod'
        self.dev = Path(self.temp.name) / 'dev'
        (self.prod / 'agent').mkdir(parents=True)
        self.dev.mkdir()
        (self.prod / 'agent/.env').write_text('LIVEKIT_API_KEY="fake-key"\nOPENAI_API_KEY=fake-openai\nCIEL_MODEL=realtime\nCIEL_NOTES_MODEL=custom\nCIEL_MINUTES_DISCORD_WEBHOOK=https://prod.invalid\n', encoding='utf-8')
        (self.prod / '.env').write_text('CIEL_DB_PASSWORD="fake-db"\nCIEL_LLM_BACKEND=local\nCIEL_INPUT=voice\n', encoding='utf-8')

    def test_separates_shared_credentials_from_production_behavior(self):
        environment.migrate(self.prod)
        shared = environment.read(self.prod / '.env.shared')
        prod = environment.read(self.prod / '.env')
        self.assertEqual(shared['LIVEKIT_API_KEY'], '"fake-key"')
        self.assertEqual(shared['CIEL_DB_PASSWORD'], '"fake-db"')
        self.assertFalse(set(shared) - environment.SHARED_KEYS)
        self.assertFalse(set(prod) & environment.SHARED_KEYS)
        self.assertEqual(prod['CIEL_NOTES_MODEL'], 'custom')
        self.assertEqual(prod.get('CIEL_MODEL', 'pipeline'), 'pipeline')
        self.assertNotIn('CIEL_LOCAL_LLM_MODEL', prod)
        self.assertEqual(prod['CIEL_LLM_BACKEND'], 'local')

    def test_development_does_not_inherit_production_backend_or_webhook(self):
        environment.migrate(self.prod, self.dev)
        dev = environment.read(self.dev / '.env.dev')
        self.assertEqual(dev['CIEL_LLM_BACKEND'], 'openai')
        self.assertEqual(dev['CIEL_MINUTES_DISCORD_WEBHOOK'], '')
        self.assertNotIn('CIEL_NOTES_MODEL', dev)

    def test_renames_development_settings_and_preserves_custom_values(self):
        (self.dev / '.env.dev').write_text('CIEL_DEV_LLM_BACKEND=local\nCIEL_DEV_INPUT=text\nCIEL_DEV_DISCORD_WEBHOOK="https://dev.invalid"\nCIEL_DEV_LOCAL_ROLES=\n', encoding='utf-8')
        environment.migrate(self.prod, self.dev)
        dev = environment.read(self.dev / '.env.dev')
        self.assertEqual(dev['CIEL_LLM_BACKEND'], 'local')
        self.assertEqual(dev['CIEL_INPUT'], 'text')
        self.assertEqual(dev['CIEL_MINUTES_DISCORD_WEBHOOK'], '"https://dev.invalid"')
        self.assertEqual(dev['CIEL_LOCAL_ROLES'], '')
        self.assertFalse(any(k.startswith('CIEL_DEV_') for k in dev))

    def test_conflict_leaves_all_files_untouched(self):
        file = self.dev / '.env.dev'
        original = 'CIEL_DEV_LLM_BACKEND=local\nCIEL_LLM_BACKEND=openai\n'
        file.write_text(original, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Conflicting development key'):
            environment.migrate(self.prod, self.dev)
        self.assertFalse((self.prod / '.env.shared').exists())
        self.assertEqual(file.read_text(), original)

    def test_runtime_settings_cannot_be_shared(self):
        (self.prod / '.env.shared').write_text('CIEL_LLM_BACKEND=local\n')
        with self.assertRaisesRegex(ValueError, 'non-shared keys'):
            environment.migrate(self.prod)

    def test_migration_is_idempotent_and_does_not_reimport_native_settings(self):
        _, backup = environment.migrate(self.prod, self.dev)
        self.assertTrue(backup.is_dir())
        self.assertTrue(any('fake-db' in p.read_text() for p in backup.iterdir()))
        (self.prod / 'agent/.env').write_text('OPENAI_API_KEY=stale\nCIEL_NOTES_MODEL=stale\n')
        self.assertEqual(environment.migrate(self.prod, self.dev), (0, None))
        self.assertEqual(environment.read(self.prod / '.env')['CIEL_NOTES_MODEL'], 'custom')

    def test_dry_run_does_not_write_or_create_backups(self):
        count, backup = environment.migrate(self.prod, self.dev, check=True)
        self.assertEqual(count, 3)
        self.assertIsNone(backup)
        self.assertFalse((self.prod / '.env.shared').exists())
        self.assertFalse((self.prod / 'data').exists())

    def test_shared_credential_conflict_never_reports_secret_values(self):
        (self.prod / '.env.shared').write_text('CIEL_DB_PASSWORD=other-private-value\n')
        with self.assertRaises(ValueError) as error:
            environment.migrate(self.prod)
        self.assertIn('CIEL_DB_PASSWORD', str(error.exception))
        self.assertNotIn('other-private-value', str(error.exception))
        self.assertNotIn('fake-db', str(error.exception))

    def test_write_failure_restores_original_files(self):
        original = (self.prod / '.env').read_bytes()
        replace = environment.os.replace
        calls = []
        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError('simulated filesystem failure')
            return replace(source, target)
        with mock.patch.object(environment.os, 'replace', side_effect=fail_second):
            with self.assertRaises(OSError):
                environment.migrate(self.prod, self.dev)
        self.assertEqual((self.prod / '.env').read_bytes(), original)
        self.assertFalse((self.prod / '.env.shared').exists())
        self.assertFalse((self.dev / '.env.dev').exists())

    def test_single_line_quotes_and_interpolation_survive_migration(self):
        (self.prod / '.env').write_text('CIEL_DB_PASSWORD="fake-db"\nCIEL_VOSK_MODELS_DIR=${HOME}/models/vosk\nCIEL_MINUTES_DISCORD_WEBHOOK="https://prod.invalid/path#fragment"\n')
        environment.migrate(self.prod)
        prod = environment.read(self.prod / '.env')
        self.assertEqual(prod['CIEL_VOSK_MODELS_DIR'], '${HOME}/models/vosk')
        self.assertEqual(prod['CIEL_MINUTES_DISCORD_WEBHOOK'], '"https://prod.invalid/path#fragment"')
