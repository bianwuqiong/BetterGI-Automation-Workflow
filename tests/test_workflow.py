import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import workflow as wf


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


class FakeProcess:
    pid = 987654
    returncode = None

    def __init__(self, stuck=False):
        self.stuck = stuck

    def poll(self):
        if not self.stuck:
            self.returncode = 0
        return self.returncode


class FakeHost:
    def __init__(self, root, *, admin=True, existing=False, stuck=False):
        self.root = root
        self.admin = admin
        self.existing = existing
        self.process = None
        self.stuck = stuck
        self.launched = False
        self.stopped = []
        self.stopped_game_pids = []
        self.memory_priorities = {}

    def is_admin(self):
        return self.admin

    def processes(self, names):
        if not self.launched:
            return [555] if self.existing else []
        if 'GenshinImpact' in names and self.process.returncode is None:
            return [888]
        return []

    def process_path(self, pid):
        return self.root / 'game.exe'

    def launch(self, exe, name):
        self.launched = True
        self.process = FakeProcess(self.stuck)
        (exe.parent / 'log/new.log').write_text(
            f'参数指定的一条龙配置：{name}\n一条龙任务执行: 1/1\n'
            '合成树脂执行异常：传送失败\n一条龙和配置组任务结束\n', encoding='utf-8')
        return self.process

    def stop_owned(self, process):
        self.stopped.append(process.pid)
        process.returncode = -1

    def stop_pids(self, pids):
        values = sorted(set(pids))
        self.stopped_game_pids.extend(values)
        return values

    def set_memory_priority(self, pid, priority):
        self.memory_priorities[int(pid)] = int(priority)

    def get_memory_priority(self, pid):
        return self.memory_priorities[int(pid)]


class ChildSessionFakeHost(FakeHost):
    ROOT_PID = 700001
    CHILD_PID = 700002
    TRIGGER_PID = 700003
    GAME_PID = 700004
    MAIN_SESSION = 5
    CHILD_SESSION = 9

    def __init__(self, root, *, stuck=False, root_elevated=True, existing_game_session=None):
        super().__init__(root, stuck=stuck)
        self.root_elevated = root_elevated
        self.existing_game_session = existing_game_session

    def current_session_id(self):
        return self.MAIN_SESSION

    def child_session_id(self):
        return self.CHILD_SESSION

    def process_session(self, pid):
        if pid in {self.ROOT_PID, self.TRIGGER_PID}:
            return self.MAIN_SESSION
        if pid in {self.CHILD_PID, self.GAME_PID}:
            return self.CHILD_SESSION
        if pid == 799999 and self.existing_game_session is not None:
            return self.existing_game_session
        raise AssertionError(f'unexpected pid {pid}')

    def process_elevated(self, pid):
        return self.root_elevated if pid == self.ROOT_PID else True

    def process_path(self, pid):
        if pid in {self.ROOT_PID, self.CHILD_PID}:
            return self.root / 'BetterGI/BetterGI.exe'
        return self.root / 'game.exe'

    def processes(self, names):
        if 'BetterGI' in names:
            values = [self.ROOT_PID, self.CHILD_PID]
            if self.launched and self.process.returncode is not None:
                values.remove(self.CHILD_PID)
            return values
        if 'GenshinImpact' in names:
            if self.existing_game_session is not None and not self.launched:
                return [799999]
            if self.launched and self.process.returncode is None:
                return [self.GAME_PID]
        return []

    def launch_child_session(self, exe, name, bettergi_names, timeout_sec=180):
        self.launched = True
        self.process = FakeProcess(self.stuck)
        self.process.pid = self.CHILD_PID
        (exe.parent / 'log/new.log').write_text(
            f'[12:01:00.000] [INF] [ChildSession:S9:P{self.CHILD_PID}:T12] Config\n'
            f'参数指定的一条龙配置：{name}\n一条龙任务执行: 1/1\n'
            '合成树脂执行异常：传送失败\n一条龙和配置组任务结束\n',
            encoding='utf-8')
        return self.process, {
            'rootBettergiPid': self.ROOT_PID,
            'triggerBettergiPid': self.TRIGGER_PID,
            'childBettergiPid': self.CHILD_PID,
            'childSessionId': self.CHILD_SESSION,
        }


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('workflow-' + uuid4().hex[:10])
        (self.root / 'config').mkdir(parents=True)
        (self.root / 'BetterGI/User/OneDragon').mkdir(parents=True)
        (self.root / 'BetterGI/log').mkdir()
        for name in ('goals.json', 'domain-calendar.json', 'book-progress.json'):
            example = name.replace('.json', '.example.json')
            (self.root / 'config' / name).write_bytes((ROOT / 'config' / example).read_bytes())
        wf.atomic_json(self.root / 'config/goals.json', {
            'allowBookCrafting': False,
            'avgGoldBooksPerRun': 1.5,
            'characters': [{
                'name': '示例角色', 'talentSeries': None, 'talents': [],
                'talentParty': '', 'artifactDomain': '示例秘境', 'artifactParty': ''
            }],
        })
        self.base_path = self.root / 'BetterGI/User/OneDragon/DailyOneDragon.json'
        self.base_path.write_bytes((ROOT / 'config/one-dragon.example.json').read_bytes())
        (self.root / 'BetterGI/User/config.json').write_bytes(
            (ROOT / 'tests/fixtures/bettergi-user-config.json').read_bytes())
        self.before = self.base_path.read_bytes()
        self.cfg = {'bettergiExe': 'BetterGI/BetterGI.exe', 'oneDragonConfig': 'DailyOneDragon',
                    'gameExe': 'game.exe', 'bettergiLogDir': 'BetterGI/log',
                    'bettergiProcessNames': ['BetterGI'], 'gameProcessNames': ['GenshinImpact'],
                    'timeoutMinutes': 1, 'gameStartTimeoutMinutes': 1, 'checkpointOnly': True,
                    'randomDelayMinutes': 0, 'pollIntervalSec': 0.01}
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        (self.root / 'BetterGI/BetterGI.exe').write_bytes(b'')
        (self.root / 'game.exe').write_bytes(b'')

    def run_flow(self, *, dry=False, task='合成树脂', host=None,
                 keep_game=False, allow_existing_game=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=task,
                                  timeout_minutes=1, no_delay=True, allow_repeat=False,
                                  keep_game=keep_game, allow_existing_game=allow_existing_game)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(wf, 'datetime', FixedClock):
            code = wf.execute(args, host or FakeHost(self.root))
        summary = json.loads(output.getvalue())
        return code, wf.read_json(summary['resultPath'])

    def test_update_genshin_general_data_sets_preset_only(self):
        graphics = {'currentVolatielGrade': -1,
                    'customVolatileGrades': [{'key': 2, 'value': 8}],
                    'volatileVersion': 'OSRELWin7.0.0'}
        raw = (json.dumps({'graphicsData': json.dumps(graphics), 'gammaValue': 2.2},
                          separators=(',', ':')).encode('utf-8') + b'\0')

        updated, previous = wf.update_genshin_general_data(raw, 1)

        root = json.loads(updated.rstrip(b'\0').decode('utf-8'))
        changed = json.loads(root['graphicsData'])
        self.assertEqual(previous, -1)
        self.assertEqual(changed['currentVolatielGrade'], 1)
        self.assertEqual(changed['customVolatileGrades'], graphics['customVolatileGrades'])
        self.assertEqual(root['gammaValue'], 2.2)

    def test_update_genshin_general_data_fails_closed(self):
        with self.assertRaises(wf.WorkflowError):
            wf.update_genshin_general_data(b'not-json\0', 1)

    def test_compatibility_profile_replaces_only_graphics_sections(self):
        profile = wf.read_json(ROOT / 'config/genshin-compat-profile.json')
        graphics = {'currentVolatielGrade': 1, 'customVolatileGrades': [],
                    'volatileVersion': profile['graphicsData']['volatileVersion']}
        perf = {'saveItems': [{'entryType': 18, 'index': 0}], 'sentinel': 'old'}
        root = {
            'graphicsData': json.dumps(graphics, separators=(',', ':')),
            'globalPerfData': json.dumps(perf, separators=(',', ':')),
            'selectedServerName': 'os_asia',
            'gammaValue': 2.2,
            'screenSettingData': {'width': 1920, 'height': 1080},
        }
        raw = json.dumps(root, separators=(',', ':')).encode() + b'\0'

        updated, previous = wf.update_genshin_general_data_profile(raw, profile)
        result = json.loads(updated.rstrip(b'\0'))

        self.assertEqual(previous['qualityLevel'], 1)
        self.assertEqual(json.loads(result['graphicsData']), profile['graphicsData'])
        self.assertEqual(json.loads(result['globalPerfData']), profile['globalPerfData'])
        self.assertEqual(result['selectedServerName'], 'os_asia')
        self.assertEqual(result['gammaValue'], 2.2)
        self.assertEqual(result['screenSettingData'], {'width': 1920, 'height': 1080})

    def test_compatibility_profile_rejects_stale_game_version(self):
        profile = wf.read_json(ROOT / 'config/genshin-compat-profile.json')
        raw = json.dumps({
            'graphicsData': json.dumps({'currentVolatielGrade': 1,
                                        'customVolatileGrades': [],
                                        'volatileVersion': 'OSRELWin8.0.0'}),
            'globalPerfData': '{}',
        }, separators=(',', ':')).encode() + b'\0'

        with self.assertRaises(wf.WorkflowError):
            wf.update_genshin_general_data_profile(raw, profile)

    def test_graphics_snapshot_excludes_identity_and_restores_only_graphics(self):
        manual = {
            'graphicsData': '{"currentVolatielGrade":5}',
            'globalPerfData': '{"saveItems":[]}',
            'gammaValue': 2.2,
            'enableHDR': False,
            'curAccountName': 'private-account',
            'targetUID': 'private-uid',
            'deviceID': 'private-device',
            'selectedServerName': 'os_asia',
        }
        snapshot = wf.make_genshin_graphics_snapshot(
            json.dumps(manual, separators=(',', ':')).encode() + b'\0',
            {'Screenmanager Resolution Width_h182942802': (2560, 4)})

        self.assertEqual(set(snapshot['generalDataFields']), {
            'graphicsData', 'globalPerfData', 'gammaValue', 'enableHDR'})
        serialized = json.dumps(snapshot, ensure_ascii=False)
        for secret in ('private-account', 'private-uid', 'private-device', 'os_asia'):
            self.assertNotIn(secret, serialized)

        current = {
            'graphicsData': '{"currentVolatielGrade":-1}',
            'globalPerfData': '{"saveItems":[1]}',
            'gammaValue': 1.0,
            'enableHDR': True,
            'curAccountName': 'current-account',
            'targetUID': 'current-uid',
            'selectedServerName': 'os_euro',
        }
        restored, changed = wf.restore_genshin_general_data(
            json.dumps(current, separators=(',', ':')).encode() + b'\0', snapshot)
        result = json.loads(restored.rstrip(b'\0'))

        self.assertEqual(set(changed), {
            'graphicsData', 'globalPerfData', 'gammaValue', 'enableHDR'})
        self.assertEqual(result['graphicsData'], manual['graphicsData'])
        self.assertEqual(result['curAccountName'], 'current-account')
        self.assertEqual(result['targetUID'], 'current-uid')
        self.assertEqual(result['selectedServerName'], 'os_euro')

    def test_graphics_snapshot_rejects_non_allowlisted_registry_value(self):
        raw = json.dumps({'graphicsData': '{}', 'globalPerfData': '{}'}).encode() + b'\0'
        with self.assertRaises(wf.WorkflowError):
            wf.make_genshin_graphics_snapshot(raw, {'AccountName': ('secret', 1)})

    def test_graphics_lease_waits_for_game_exit_then_recovers(self):
        snapshot = wf.make_genshin_graphics_snapshot(
            json.dumps({'graphicsData': '{}', 'globalPerfData': '{}'}).encode() + b'\0')
        directory = self.root / 'logs/runs/20260912T120000-12345678'
        directory.mkdir(parents=True)
        with patch.object(wf, 'snapshot_genshin_graphics_settings', return_value=snapshot):
            lease = wf.begin_graphics_lease(
                self.root, directory, '20260912T120000-12345678')
        with patch.object(wf, 'restore_genshin_graphics_settings') as restore:
            pending = wf.finish_graphics_lease(self.root, lease, [4321])
            self.assertFalse(pending['restored'])
            restore.assert_not_called()
        with self.assertRaises(wf.WorkflowError):
            wf.recover_pending_graphics_lease(self.root, [4321])
        restored_result = {
            'restored': True, 'restoredAt': '2026-09-12T12:01:00+00:00',
            'changedGeneralFields': ['graphicsData'], 'changedRegistryValues': []}
        with patch.object(wf, 'restore_genshin_graphics_settings',
                          return_value=restored_result) as restore:
            recovered = wf.recover_pending_graphics_lease(self.root, [])
            restore.assert_called_once_with(snapshot)
        self.assertTrue(recovered['restored'])
        self.assertEqual(wf.read_json(
            self.root / 'state/graphics-profile-lease.json')['state'], 'recovered')

    def test_live_graphics_profile_is_restored_after_failed_task(self):
        profile_path = self.root / 'config/genshin-compat-profile.json'
        profile_path.write_bytes((ROOT / 'config/genshin-compat-profile.json').read_bytes())
        self.cfg.update(gameGraphicsProfile='config/genshin-compat-profile.json',
                        gameGraphicsQualityLevel=None,
                        restoreManualGraphicsAfterRun=True)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        snapshot = wf.make_genshin_graphics_snapshot(
            json.dumps({'graphicsData': '{}', 'globalPerfData': '{}'}).encode() + b'\0')
        restored_result = {
            'restored': True, 'restoredAt': '2026-09-12T12:01:00+00:00',
            'changedGeneralFields': ['graphicsData'], 'changedRegistryValues': []}
        with (patch.object(wf, 'snapshot_genshin_graphics_settings', return_value=snapshot),
              patch.object(wf, 'ensure_genshin_graphics_profile',
                           return_value={'changed': True}),
              patch.object(wf, 'restore_genshin_graphics_settings',
                           return_value=restored_result) as restore):
            code, result = self.run_flow()

        self.assertNotEqual(code, 0)
        restore.assert_called_once_with(snapshot)
        self.assertTrue(result['graphicsIsolation']['restored'])
        self.assertEqual(wf.read_json(
            self.root / 'state/graphics-profile-lease.json')['state'], 'restored')

    def test_dry_run_preserves_base_and_previous_result(self):
        wf.atomic_json(self.root / 'results.json', {'sentinel': 42})
        host = FakeHost(self.root, admin=False)
        code, result = self.run_flow(dry=True, host=host)
        self.assertEqual(code, 0)
        self.assertEqual(result['outcome'], 'planned')
        self.assertFalse(host.launched)
        self.assertEqual(self.base_path.read_bytes(), self.before)
        self.assertEqual(wf.read_json(self.root / 'results.json'), {'sentinel': 42})
        self.assertEqual(len(list(self.base_path.parent.glob('*.json'))), 1)
        generated = wf.read_json(result['plannedConfig'])
        self.assertEqual(sum(generated['TaskEnabledList'].values()), 1)

    def test_failure_run_never_completes_and_only_writes_own_config(self):
        code, result = self.run_flow()
        self.assertNotEqual(code, 0)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['executionOutcome'], 'exited')
        self.assertEqual(self.base_path.read_bytes(), self.before)
        self.assertTrue(Path(result['runtimeConfig']).is_file())
        self.assertEqual(sum(wf.read_json(result['runtimeConfig'])['TaskEnabledList'].values()), 1)

    def test_preflight_failure_replaces_old_success(self):
        wf.atomic_json(self.root / 'results.json', {'outcome': 'completed', 'runId': 'old'})
        code, result = self.run_flow(host=FakeHost(self.root, admin=False))
        self.assertEqual(code, 2)
        self.assertEqual(wf.read_json(self.root / 'results.json')['outcome'], 'failed')
        self.assertNotEqual(result['runId'], 'old')

    def test_live_existing_process_is_not_adopted(self):
        host = FakeHost(self.root, existing=True)
        code, result = self.run_flow(host=host)
        self.assertEqual(code, 6)
        self.assertFalse(host.launched)
        self.assertEqual(host.stopped, [])

    def test_checkpoint_gate_blocks_whole_daily(self):
        host = FakeHost(self.root)
        code, result = self.run_flow(task=None, host=host)
        self.assertEqual(code, 4)
        self.assertFalse(host.launched)
        self.assertIn('检查点', ' '.join(result['errors']))

    def test_timeout_stops_only_owned_process_and_keeps_config(self):
        host = FakeHost(self.root, stuck=True)
        with patch.object(wf.time, 'monotonic', side_effect=[0, 1000, 1001]):
            code, result = self.run_flow(host=host)
        self.assertEqual(code, 3)
        self.assertEqual(result['executionOutcome'], 'timeout')
        self.assertNotEqual(result['outcome'], 'completed')
        self.assertEqual(host.stopped, [987654])
        self.assertEqual(host.stopped_game_pids, [888])
        self.assertEqual(self.base_path.read_bytes(), self.before)

    def test_child_session_mode_tracks_child_and_preserves_root(self):
        self.cfg['executionMode'] = 'childSession'
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        host = ChildSessionFakeHost(self.root)

        code, result = self.run_flow(host=host)

        self.assertNotEqual(code, 0)
        self.assertTrue(host.launched)
        self.assertEqual(result['executionMode'], 'childSession')
        self.assertEqual(result['bettergiPid'], host.CHILD_PID)
        self.assertEqual(result['rootBettergiPid'], host.ROOT_PID)
        self.assertEqual(result['childSessionId'], host.CHILD_SESSION)
        self.assertNotIn(host.ROOT_PID, host.stopped)

    def test_child_session_timeout_stops_only_child(self):
        self.cfg['executionMode'] = 'childSession'
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        host = ChildSessionFakeHost(self.root, stuck=True)

        with patch.object(wf.time, 'monotonic', side_effect=[0, 1000, 1001]):
            code, result = self.run_flow(host=host)

        self.assertEqual(code, 3)
        self.assertEqual(result['executionOutcome'], 'timeout')
        self.assertEqual(host.stopped, [host.CHILD_PID])
        self.assertEqual(host.stopped_game_pids, [host.GAME_PID])
        self.assertNotIn(host.ROOT_PID, host.stopped)

    def test_child_session_rejects_low_integrity_root_and_existing_game(self):
        self.cfg['executionMode'] = 'childSession'
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)

        low_host = ChildSessionFakeHost(self.root, root_elevated=False)
        low_code, low_result = self.run_flow(host=low_host)
        self.assertEqual(low_code, 6)
        self.assertFalse(low_host.launched)
        self.assertIn('管理员权限', ' '.join(low_result['errors']))

        game_host = ChildSessionFakeHost(
            self.root,
            existing_game_session=ChildSessionFakeHost.MAIN_SESSION)
        game_code, game_result = self.run_flow(host=game_host)
        self.assertEqual(game_code, 6)
        self.assertFalse(game_host.launched)
        self.assertIn('已经运行', ' '.join(game_result['errors']))

    def test_lock_rejects_other_process_and_does_not_replace_current(self):
        wf.atomic_json(self.root / 'results.json', {'runId': 'active-owner'})
        with wf.RunLock(self.root / 'state/workflow.lock'):
            code, result = self.run_flow(dry=False)
            probe = (
                'import sys; from pathlib import Path; '
                f'sys.path.insert(0, {str(ROOT / "scripts")!r}); '
                'from workflow import RunLock,WorkflowError\n'
                f'try:\n with RunLock(Path({str(self.root / "state/workflow.lock")!r})): pass\n'
                'except WorkflowError as e: sys.exit(e.code)\n'
            )
            child = subprocess.run([sys.executable, '-B', '-c', probe], capture_output=True)
        self.assertEqual(code, 6)
        self.assertEqual(child.returncode, 6)
        self.assertEqual(wf.read_json(self.root / 'results.json')['runId'], 'active-owner')

    def test_patch_cannot_enable_extra_tasks_or_change_name(self):
        template = wf.read_json(self.base_path)
        selected, _ = wf.task_selection(template, '合成树脂')
        for patch_value in ({'TaskEnabledList': {}}, {'Name': 'other'}, {'SundayEverySelectedValue': '99'}):
            with self.assertRaises(wf.WorkflowError):
                wf.make_config(template, selected, 'test', patch_value)

    def test_current_partial_success_is_also_protected_from_repeat(self):
        wf.atomic_json(self.root / 'logs/runs/previous/result.json',
                       {'runId': 'previous', 'gameDate': '2026-09-12', 'outcome': 'partial',
                        'mode': 'daily', 'tasks': [{'name': '合成树脂', 'status': 'success'}]})
        self.assertEqual(wf.prior_success(self.root, '2026-09-12', ['合成树脂']), 'previous')

    def test_only_fresh_owned_log_records_are_read(self):
        directory = self.root / 'BetterGI/log'
        path = directory / 'sample.log'
        path.write_text('old data\n', encoding='utf-8')
        offsets = wf.log_offsets(directory)
        with path.open('a', encoding='utf-8') as stream:
            stream.write('[12:01:00.000] [INF] [Primary:S4:P987654:T12] Logger\nours\n')
            stream.write('[12:01:01.000] [INF] [Primary:S4:P111:T12] Logger\nother\n')
        value, _ = wf.collect_log(directory, offsets, 987654)
        self.assertIn('ours', value)
        self.assertNotIn('old data', value)
        self.assertNotIn('other', value)

    def test_fragile_resin_policy_blocks_conflicting_config(self):
        with self.assertRaises(wf.WorkflowError):
            wf.check_resource_policy({'autoLeyLineOutcropConfig': {'useFragileResin': True}}, ['自动地脉花'])

    def test_excessive_timeout_cannot_bypass_scheduler_budget(self):
        host = FakeHost(self.root)
        args = argparse.Namespace(root=str(self.root), dry_run=False, task='合成树脂',
                                  timeout_minutes=150, no_delay=True, allow_repeat=False)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(wf, 'datetime', FixedClock):
            code = wf.execute(args, host)
        self.assertEqual(code, 4)
        self.assertFalse(host.launched)

    def test_stop_request_stops_owned_run_without_waiting_for_timeout(self):
        outer = self

        class StoppingHost(FakeHost):
            def launch(self, exe, name):
                process = super().launch(exe, name)
                current = wf.read_json(outer.root / 'state/current-run.json')
                wf.atomic_json(outer.root / 'logs/runs' / current['runId'] / 'stop-request.json', {'stop': True})
                return process

        host = StoppingHost(self.root, stuck=True)
        code, result = self.run_flow(host=host)
        self.assertEqual(code, 9)
        self.assertEqual(result['executionOutcome'], 'cancelled')
        self.assertEqual(host.stopped, [987654])

    def test_model_response_cannot_invent_evidence_or_execute_commands(self):
        packet = wf.packet_for({'runId': 'r1', 'tasks': [{'name': '合成树脂', 'status': 'failed',
                                'evidence': [{'line': 5, 'text': '传送失败'}]}]})
        response = {'runId': 'r1', 'recommendation': 'recommend_single_task_retry', 'task': '合成树脂',
                    'reason': '缺少画面证据', 'evidenceLines': [5], 'needsMoreEvidence': True}
        checked = wf.validate_recommendation(packet, response)
        self.assertEqual(checked['effectiveRecommendation'], 'inspect_evidence')
        self.assertFalse(checked['executed'])
        for bad in (dict(response, runId='old'), dict(response, evidenceLines=[999]),
                    dict(response, command='start-game'), dict(response, task='未请求的任务')):
            with self.assertRaises(wf.WorkflowError):
                wf.validate_recommendation(packet, bad)

    def test_keep_game_uses_no_completion_action(self):
        template = wf.read_json(self.base_path)
        selected, _ = wf.task_selection(template, '领取邮件')
        generated = wf.make_config(template, selected, 'diag', {}, '无')
        self.assertEqual(generated['CompletionAction'], '无')
        with self.assertRaises(wf.WorkflowError):
            wf.make_config(template, selected, 'diag', {}, '关机')

    def test_existing_game_override_requires_keep_open_checkpoint(self):
        class GameOnlyHost(FakeHost):
            def processes(self, names):
                return [555] if 'GenshinImpact' in names and not self.launched else []

        args = argparse.Namespace(root=str(self.root), dry_run=False, task=None, profile='core',
                                  timeout_minutes=1, no_delay=True, allow_repeat=False,
                                  keep_game=True, allow_existing_game=True)
        host = GameOnlyHost(self.root)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(wf, 'datetime', FixedClock):
            code = wf.execute(args, host)
        self.assertEqual(code, 4)
        self.assertFalse(host.launched)

    def test_existing_game_override_records_unique_path_matched_pid(self):
        class AdoptedHost(FakeHost):
            def processes(self, names):
                return [555] if 'GenshinImpact' in names else []

        host = AdoptedHost(self.root)
        code, result = self.run_flow(host=host, task='领取邮件', keep_game=True,
                                     allow_existing_game=True)
        self.assertTrue(host.launched)
        self.assertEqual(result['adoptedGamePid'], 555)
        self.assertEqual(Path(result['adoptedGameExe']), self.root / 'game.exe')

    def test_existing_game_override_rejects_multiple_processes(self):
        class MultipleGamesHost(FakeHost):
            def processes(self, names):
                return [555, 556] if 'GenshinImpact' in names else []

        host = MultipleGamesHost(self.root)
        code, result = self.run_flow(host=host, task='领取邮件', keep_game=True,
                                     allow_existing_game=True)
        self.assertEqual(code, 6)
        self.assertFalse(host.launched)
        self.assertIn('只能存在一个', ' '.join(result['errors']))

    def test_existing_game_override_rejects_wrong_executable(self):
        class WrongGameHost(FakeHost):
            def processes(self, names):
                return [555] if 'GenshinImpact' in names else []

            def process_path(self, pid):
                return self.root / 'other-game.exe'

        host = WrongGameHost(self.root)
        code, result = self.run_flow(host=host, task='领取邮件', keep_game=True,
                                     allow_existing_game=True)
        self.assertEqual(code, 6)
        self.assertFalse(host.launched)
        self.assertIn('路径', ' '.join(result['errors']))

    def test_existing_game_override_stops_if_pid_changes_during_monitoring(self):
        class ReplacedGameHost(FakeHost):
            def __init__(self, root):
                super().__init__(root, stuck=True)
                self.game_checks = 0

            def processes(self, names):
                if 'GenshinImpact' not in names:
                    return []
                self.game_checks += 1
                return [555] if self.game_checks <= 5 else [556]

        host = ReplacedGameHost(self.root)
        code, result = self.run_flow(host=host, task='领取邮件', keep_game=True,
                                     allow_existing_game=True)
        self.assertEqual(code, 6)
        self.assertTrue(host.launched)
        self.assertEqual(host.stopped, [987654])
        self.assertEqual(result['executionOutcome'], 'adopted_game_changed')
        self.assertIn('退出或被替换', ' '.join(result['errors']))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows process enumeration')
    def test_windows_process_enumeration_uses_native_snapshot(self):
        host = wf.WindowsHost()
        found = host.processes([Path(sys.executable).stem])
        self.assertIn(__import__('os').getpid(), found)
        self.assertTrue(wf.same_executable_path(host.process_path(__import__('os').getpid()), sys.executable))

    def test_core_profile_omits_extras_without_modifying_base(self):
        template = wf.read_json(self.base_path)
        selected, names = wf.task_selection(template, profile='core')
        self.assertEqual(names, ['合成树脂', '自动秘境', '领取每日奖励'])
        self.assertEqual(self.base_path.read_bytes(), self.before)
        self.assertEqual(len(selected), 3)
        self.assertEqual(wf.task_selection(template, profile='extras')[1], ['领取邮件', '自动地脉花', '领取尘歌壶奖励'])

    def test_time_budget_separates_target_and_stop_limit(self):
        cfg = {'coreTargetMinutes': 20, 'profileTimeoutMinutes': {'core': 25},
               'maximumRunMinutes': 30, 'taskTimeoutMinutes': {'合成树脂': 5}}
        self.assertEqual(wf.time_budget(cfg, None, 'core'), {'maximumMinutes': 25, 'targetMinutes': 20})
        self.assertEqual(wf.time_budget(cfg, '合成树脂', 'core')['maximumMinutes'], 5)

    def test_stalled_tree_search_stops_before_total_timeout(self):
        class TreeHost(FakeHost):
            def launch(self, exe, name):
                process = super().launch(exe, name)
                (exe.parent / 'log/new.log').write_text(
                    f'[12:00:00.000] [INF]\n参数指定的一条龙配置：{name}\n一条龙任务执行: 1/1\n'
                    '自动秘境："1. 走到钥匙处启动"\n'
                    '[12:00:01.000] [INF]\n自动秘境："2. 执行战斗策略"\n'
                    '[12:00:02.000] [INF]\n自动秘境："3. 寻找石化古树"\n', encoding='utf-8')
                return process

        self.cfg['stageMaximumSec'] = {'tree_search': 90}
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        host = TreeHost(self.root, stuck=True)
        args = argparse.Namespace(root=str(self.root), dry_run=False, task='自动秘境',
                                  timeout_minutes=5, no_delay=True, allow_repeat=False)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(wf, 'datetime', FixedClock), patch.object(wf.time, 'monotonic', side_effect=[0, 100, 101]):
            code = wf.execute(args, host)
        result = wf.read_json(self.root / 'results.json')
        self.assertEqual(code, 3)
        self.assertEqual(result['executionOutcome'], 'stage_timeout')
        self.assertEqual(host.stopped, [987654])
        self.assertEqual(host.stopped_game_pids, [888])
        self.assertNotEqual(result['outcome'], 'completed')


if __name__ == '__main__':
    unittest.main()
