import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('dev_minecraft_setup',Path(__file__).resolve().parents[2]/'minecraft/dev-setup.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class DevelopmentMinecraftSetupTest(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.data=self.root/'minecraft/data';self.data.mkdir(parents=True)
        (self.root/'.env.minecraft').write_text('MINECRAFT_EULA=TRUE\nMC_OWNER=Owner\n')
        (self.data/'server.properties').write_text('online-mode=false\nwhite-list=true\n')
        (self.data/'whitelist.json').write_text(json.dumps([{'name':'Owner','uuid':'existing-owner'}]))

    def test_preserves_existing_entries_and_only_reloads_whitelist(self):
        with patch.object(setup.subprocess,'run')as run:
            setup.configure(self.root)
            rows=json.loads((self.data/'whitelist.json').read_text())
            self.assertEqual(rows[0],{'name':'Owner','uuid':'existing-owner'})
            self.assertEqual(rows[1]['name'],'Ciel_Dev')
            before=(self.data/'whitelist.json').read_bytes()
            setup.configure(self.root)
            self.assertEqual(before,(self.data/'whitelist.json').read_bytes())
            self.assertEqual(len(list((self.data/'ciel-config-backups').glob('*.json'))),1)
            self.assertEqual(run.call_args.args[0],['docker','exec','ciel-minecraft-1','rcon-cli','whitelist','reload'])

    def test_refuses_online_server_or_identity_conflict_before_changes(self):
        original=(self.data/'whitelist.json').read_bytes()
        (self.data/'server.properties').write_text('online-mode=true\nwhite-list=true\n')
        with self.assertRaises(RuntimeError):setup.configure(self.root)
        self.assertEqual(original,(self.data/'whitelist.json').read_bytes())
        (self.data/'server.properties').write_text('online-mode=false\nwhite-list=true\n')
        (self.data/'whitelist.json').write_text(json.dumps([{'name':'Ciel_Dev','uuid':'wrong'}]))
        with self.assertRaises(RuntimeError):setup.configure(self.root)
