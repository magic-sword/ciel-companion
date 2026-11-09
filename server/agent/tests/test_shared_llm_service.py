"""Shared inference capacity and benchmark isolation, without external services."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import tempfile
import tarfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

class SharedServiceTest(unittest.TestCase):
    def test_staging_refreshes_provenance_timestamp_and_excludes_credentials(self):
        helper=module('benchmark_home_stage','scripts/server/benchmark-home.py')
        class Buffer(io.BytesIO):
            def close(self):
                pass
        class Process:
            stdin=Buffer()
            def wait(self):
                return 0
        process=Process()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'server').mkdir()
            (root/'server/.env').write_text('private')
            with patch.object(helper,'ROOT',root),patch.object(helper,'provenance',return_value={'git_commit':'current'}), \
                    patch.object(helper,'ssh_args',return_value=['ssh']),patch.object(helper.subprocess,'Popen',return_value=process), \
                    patch.object(helper,'remote'):
                helper.stage()
        with tarfile.open(fileobj=io.BytesIO(process.stdin.getvalue())) as archive:
            self.assertNotIn('.env',archive.getnames())
            member=archive.getmember('benchmark/staged-provenance.json')
            self.assertGreater(member.mtime,0)
            self.assertEqual(json.load(archive.extractfile(member))['git_commit'],'current')

    def test_shared_smoke_never_starts_an_extra_model(self):
        helper=module('benchmark_home_shared','scripts/server/benchmark-home.py')
        with patch.object(helper,'remote') as remote:
            helper.smoke('conversation',seconds=180)
        code=remote.call_args.args[0]
        compile(code,'remote smoke','exec')
        self.assertNotIn("run('up','-d','llm-bench')",code)
        self.assertIn('http://127.0.0.1:8094/v1',code)
        self.assertIn("status.get('mode')!='gpu'",code)
        with patch.object(helper,'remote') as remote:
            helper.smoke('conversation',llm_service='dedicated')
        code=remote.call_args.args[0]
        compile(code,'dedicated smoke','exec')
        self.assertIn("run('up','-d','llm-bench')",code)
        self.assertIn('http://127.0.0.1:8096/v1',code)

    def test_actual_server_capacity_is_recorded_and_short_context_rejected(self):
        from benchmark.run import inference_server_info
        env={'CIEL_BENCH_LLM_URL':'http://127.0.0.1:8094/v1','CIEL_BENCH_LLM_SERVICE':'shared','CIEL_BENCH_LLM_CONTROL':'http://127.0.0.1:8095'}
        props={'default_generation_settings':{'n_ctx':32768},'total_slots':2,'model_path':'/models/test.gguf'}
        responses=[io.BytesIO(json.dumps(value).encode()) for value in (props,{'mode':'gpu','ready':True})]
        with patch.dict(os.environ,env), patch('benchmark.run.urllib.request.urlopen',side_effect=responses):
            info=inference_server_info()
        self.assertEqual(info,{'service':'shared','context':32768,'parallel':2,'model':'test.gguf','mode':'gpu','ready':True})
        props['default_generation_settings']['n_ctx']=12288
        with patch.dict(os.environ,env), patch('benchmark.run.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(props).encode())):
            with self.assertRaisesRegex(RuntimeError,'32768'):
                inference_server_info()

    def test_supervisor_preserves_cpu_isolation_and_explicit_gpu_capacity(self):
        env={'LOCAL_LLM_CTX':'32768','LOCAL_LLM_PARALLEL':'2','LOCAL_LLM_GPU_LAYERS':'99','LOCAL_LLM_CPU_MOE_LAYERS':'38'}
        with patch.dict(os.environ,env):
            supervisor=module('shared_supervisor','server/local-llm/supervisor.py')
        with patch.object(supervisor.subprocess,'Popen') as popen:
            supervisor._start('gpu')
            command=popen.call_args.args[0]
            self.assertIn('--parallel',command)
            self.assertEqual(command[command.index('--parallel')+1],'2')
            self.assertEqual(command[command.index('-c')+1],'65536')
            self.assertEqual(command[command.index('--n-cpu-moe')+1],'38')
            supervisor._start('cpu')
            self.assertEqual(popen.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'],'')

    def test_remote_management_scripts_compile(self):
        helper=module('shared_home','scripts/server/shared-llm-home.py')
        compile(helper.COMMON+helper.CONFIGURE,'configure','exec')
        compile(helper.COMMON+helper.PROBE,'probe','exec')

if __name__=='__main__':
    unittest.main()
