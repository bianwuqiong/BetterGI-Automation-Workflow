import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from scripts.recording_readiness import main
from scripts.recording_readiness import recording_startup_ready, READY


class RecordingReadinessTests(unittest.TestCase):
    config = '[12:00:00.001] [INF] [Primary:S1:P99:T1] BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel\n启用一条龙配置：AutoGame_run\n'
    ready = '[12:00:01.001] [INF] [Primary:S1:P99:T1] BetterGenshinImpact.GameTask.Common.TaskControl\n'+READY+'\n'

    def test_recording_starts_after_current_native_startup(self):
        self.assertTrue(recording_startup_ready(self.config+self.ready,99,'AutoGame_run'))

    def test_other_process_or_configuration_and_ocr_text_cannot_start_recording(self):
        for text in (self.ready, self.config+self.ready.replace('P99','P98'),
                     self.config.replace('ViewModel.Pages.OneDragonFlowViewModel','ViewModel.Pages.OcrScanViewModel')+self.ready,
                     self.config.replace('AutoGame_run','AutoGame_old')+self.ready,
                     self.config+self.ready.replace('GameTask.Common.TaskControl','ViewModel.Pages.OcrScanViewModel'),
                     self.config+self.ready.replace('\n'+READY,'\nOCR结果：'+READY)):
            with self.subTest(text=text):
                self.assertFalse(recording_startup_ready(text,99,'AutoGame_run'))

    def test_cli_reads_the_actual_log_directory_and_never_records_finished_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'logs/runs/run';directory.mkdir(parents=True)
            logs=root/'native-log';logs.mkdir()
            log=logs/'current.log';log.write_text(self.config+self.ready,encoding='utf-8')
            (directory/'log-offsets.json').write_text(json.dumps({str(log):0}),encoding='utf-8')
            result=directory/'result.json'
            result.write_text(json.dumps(dict(runId='run',outcome='running',bettergiPid=99)),encoding='utf-8')
            with patch('sys.argv',['recording_readiness','--root',str(root),'--run-id','run']):
                self.assertEqual(main(),0)
                result.write_text(json.dumps(dict(runId='run',outcome='unknown',bettergiPid=99)),encoding='utf-8')
                self.assertEqual(main(),1)
