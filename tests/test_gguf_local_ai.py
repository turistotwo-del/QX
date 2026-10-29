"""Tests for optional real offline GGUF inference without a model download."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from types import SimpleNamespace

from modern import local_ai


class TestGGUFLocalAI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qx_gguf_test_')
        self.dir = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'QX_AI_MODEL_DIR': str(self.dir)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.temp.cleanup)
        local_ai._GGUF_INSTANCE.update({'path':None,'stamp':None,'instance':None})

    def make_model(self, name='qx-test.gguf'):
        (self.dir/name).write_bytes(b'GGUF' + b'\x00'*128)
        return name

    def test_detects_only_valid_local_gguf(self):
        self.make_model()
        (self.dir/'fake.gguf').write_bytes(b'NOT_GGUF')
        (self.dir/'program.exe').write_bytes(b'GGUF'+b'\x00'*50)
        self.assertEqual(local_ai.gguf_model_names(), ['qx-test.gguf'])

    def test_symlink_escape_not_a_model(self):
        with tempfile.TemporaryDirectory() as outer:
            target=Path(outer)/'private.gguf'
            target.write_bytes(b'GGUF'+b'\x00'*128)
            try: (self.dir/'private.gguf').symlink_to(target)
            except (OSError,NotImplementedError): self.skipTest('No symlinks permitted')
            self.assertEqual(local_ai.gguf_model_names(), [])

    def test_model_list_combines_ollama_and_gguf(self):
        self.make_model()
        response = SimpleNamespace(
            __enter__=lambda self: self,
            __exit__=lambda self,*args:None)
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,*args): return json.dumps({'models':[{'name':'qwen2.5:3b'}]}).encode()
        with patch.object(local_ai,'urlopen',return_value=FakeResponse()), \
             patch.object(local_ai,'gguf_runtime_available',return_value=True):
            info=local_ai.available_models()
        self.assertEqual(set(info['models']), {'qwen2.5:3b','gguf:qx-test.gguf'})
        self.assertTrue(info['available'])

    def test_gguf_selected_without_network(self):
        self.make_model()
        calls=[]
        class FakeLlama:
            def __init__(self,**kwargs): calls.append(kwargs)
            def create_completion(self,**kwargs):
                calls.append(kwargs)
                return {'choices':[{'text':'Реестровый BIOS требуется (contract.txt, строка 1).'}]}
        with patch.object(local_ai,'gguf_runtime_available',return_value=True), \
             patch.dict(sys.modules, {'llama_cpp':SimpleNamespace(Llama=FakeLlama)}), \
             patch.object(local_ai,'urlopen',side_effect=AssertionError('Unexpected network')):
            answer=local_ai.local_question([('contract.txt','В контракте требуется реестровый BIOS.'.encode())],
                                           'Нужен ли реестровый BIOS?', 'gguf:qx-test.gguf')
        self.assertIn('GGUF',answer['mode'])
        self.assertIn('Реестровый',answer['text'])
        self.assertEqual(calls[0]['n_gpu_layers'],0)

    def test_chat_template_is_used_instead_of_raw_completion(self):
        self.make_model()
        history=[]
        class FakeLlama:
            def __init__(self,**kwargs):pass
            def create_chat_completion(self,**kwargs):
                history.append(kwargs)
                return {'choices':[{'message':{'content':'Реестровый BIOS требуется [ТЗ.txt; строка 1]'}}]}
            def create_completion(self,**kwargs):
                raise AssertionError('Raw completion does not honor Qwen chat template')
        with patch.object(local_ai,'gguf_runtime_available',return_value=True), \
             patch.dict(sys.modules, {'llama_cpp':SimpleNamespace(Llama=FakeLlama)}):
            answer=local_ai.local_question([('ТЗ.txt','Реестровый BIOS требуется.'.encode())],
                                           'Нужен ли BIOS?', 'gguf:qx-test.gguf')
        self.assertEqual(history[0]['messages'][0]['role'],'system')
        self.assertEqual(history[0]['messages'][1]['role'],'user')
        self.assertIn('Реестровый',answer['text'])
        self.assertNotIn('нет среди',answer['warning'])

    def test_arbitrary_paths_are_rejected(self):
        self.make_model()
        with self.assertRaises(ValueError):
            local_ai._gguf_answer('gguf:../../outside.gguf','test')
        with self.assertRaises(ValueError):
            local_ai._gguf_answer('gguf:/etc/passwd','test')


if __name__=='__main__': unittest.main()
