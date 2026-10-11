import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import workflow as wf

class AtomicStatusTests(unittest.TestCase):
    def setUp(self):
        self.directory=ROOT/'tests/.artifacts'/('atomic-status-'+uuid4().hex[:8])
        self.directory.mkdir(parents=True)
        self.path=self.directory/'status.json'
        self.path.write_text('{"old":true}',encoding='utf-8')

    @staticmethod
    def locked(code=32):
        error=PermissionError('Windows file temporarily held')
        error.winerror=code
        return error

    def test_transient_windows_reader_retries_without_losing_old_or_new(self):
        original=wf.os.replace
        calls=[]
        def replace(source,destination):
            calls.append((source,destination))
            if len(calls)<3:
                self.assertEqual(json.loads(self.path.read_text()),{'old':True})
                raise self.locked()
            return original(source,destination)
        with patch.object(wf.os,'replace',side_effect=replace),patch.object(wf.time,'sleep') as delay:
            wf.atomic_json(self.path,{'runId':'synthetic-current','outcome':'running'})
        self.assertEqual(len(calls),3)
        self.assertEqual(delay.call_count,2)
        self.assertEqual(json.loads(self.path.read_text())['runId'],'synthetic-current')
        self.assertEqual(len({source for source,_ in calls}),1)

    def test_permanent_windows_denial_stays_bounded_and_keeps_recovery_copy(self):
        with patch.object(wf.os,'replace',side_effect=self.locked(5)) as replace,patch.object(wf.time,'sleep') as delay:
            with self.assertRaises(PermissionError):wf.atomic_json(self.path,{'new':True})
        self.assertEqual(replace.call_count,8)
        self.assertEqual(delay.call_count,7)
        self.assertEqual(json.loads(self.path.read_text()),{'old':True})
        copies=list(self.directory.glob('status.json.*.tmp'))
        self.assertEqual(len(copies),1)
        self.assertEqual(json.loads(copies[0].read_text()),{'new':True})

    def test_unrelated_os_error_is_not_retried(self):
        with patch.object(wf.os,'replace',side_effect=OSError('disk failure')) as replace,patch.object(wf.time,'sleep') as delay:
            with self.assertRaises(OSError):wf.atomic_json(self.path,{'new':True})
        self.assertEqual(replace.call_count,1)
        delay.assert_not_called()
