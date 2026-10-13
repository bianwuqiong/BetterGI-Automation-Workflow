import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock
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

    def hot_switch_game_input(self, game_pids):
        return False


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


def native_startup_log(name, pid, *, failure='一条龙启动核验失败，未执行任务节点'):
    return (
        f'[12:01:00.000] [INF] [Primary:S4:P{pid}:T123456] '
        'BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel\n'
        f'参数指定的一条龙配置：{name}\n\n'
        f'[12:04:00.000] [ERR] [Primary:S4:P{pid}:T123456] '
        'BetterGenshinImpact.Service.ScriptService\n'
        '启动等待超时，禁止执行任务节点：模式=BitBlt，尺寸=1920x1080\n\n'
        f'[12:04:00.010] [ERR] [Primary:S4:P{pid}:T123456] '
        'BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel\n'
        f'{failure}\nSystem.TimeoutException: startup deadline\n\n')


class StartupFailureFakeHost(FakeHost):
    def launch(self, exe, name):
        self.launched = True
        self.process = FakeProcess(stuck=True)
        (exe.parent / 'log/new.log').write_text(
            native_startup_log(name, self.process.pid), encoding='utf-8')
        return self.process


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/.artifacts' / ('workflow-' + uuid4().hex[:10])
        (self.root / 'config').mkdir(parents=True)
        (self.root / 'BetterGI/User/OneDragon').mkdir(parents=True)
        (self.root / 'BetterGI/log').mkdir()
        wf.atomic_json(self.root / 'config/goals.json', {
            'allowBookCrafting': False,
            'avgGoldBooksPerRun': 1.5,
            'characters': [{
                'name': '钟离',
                'characterId': 10000030,
                'priority': 1,
                'domains': [{
                    'domain': '太山府',
                    'dayOfWeek': [3, 6, 7],
                    'rewardIndex': 1,
                    'bookSeries': '黄金'
                }],
                'talentParty': '',
                'artifactDomain': '逆悬的冰河',
                'artifactParty': ''
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
                 keep_game=False, allow_existing_game=False, graphics_check=False):
        args = argparse.Namespace(root=str(self.root), dry_run=dry, task=task,
                                  timeout_minutes=1, no_delay=True, allow_repeat=False,
                                  keep_game=keep_game, allow_existing_game=allow_existing_game,
                                  graphics_check=graphics_check)
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

    def test_automation_display_requires_windowed_16_by_9_values(self):
        expected = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        self.assertEqual(wf.normalize_genshin_display_settings(expected), expected)
        values = wf._genshin_display_registry_values(expected)
        self.assertEqual(values[wf.GENSHIN_DISPLAY_REGISTRY_NAMES['width']], 1920)
        self.assertEqual(values[wf.GENSHIN_DISPLAY_REGISTRY_NAMES['height']], 1080)
        self.assertEqual(values[wf.GENSHIN_DISPLAY_REGISTRY_NAMES['windowed']], 0)
        for bad in (
                {'width': 1920, 'height': 1200, 'windowed': True},
                {'width': 1920, 'height': 1080, 'windowed': 'yes'},
                {'width': 640, 'height': 360, 'windowed': True},
                {'width': 1920, 'height': 1080, 'windowed': True, 'unknown': 1}):
            with self.assertRaises(wf.WorkflowError):
                wf.normalize_genshin_display_settings(bad)

    def test_graphics_verification_compares_profile_and_display_without_identity(self):
        profile = wf.read_json(ROOT / 'config/genshin-compat-profile.json')
        raw = json.dumps({
            'graphicsData': json.dumps(profile['graphicsData'], separators=(',', ':')),
            'globalPerfData': json.dumps(profile['globalPerfData'], separators=(',', ':')),
            'curAccountName': 'private-account',
            'targetUID': 'private-uid',
        }, separators=(',', ':')).encode() + b'\0'
        display = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        values = wf._genshin_display_registry_values(display)

        result = wf.assess_genshin_automation_graphics(
            raw, profile=profile, registry_values=values, display_settings=display)

        self.assertTrue(result['allMatched'])
        self.assertTrue(result['compatibleProfileMatched'])
        self.assertTrue(result['displayRegistryMatched'])
        serialized = json.dumps(result)
        self.assertNotIn('private-account', serialized)
        self.assertNotIn('private-uid', serialized)
        values[wf.GENSHIN_DISPLAY_REGISTRY_NAMES['width']] = 2560
        mismatch = wf.assess_genshin_automation_graphics(
            raw, profile=profile, registry_values=values, display_settings=display)
        self.assertFalse(mismatch['allMatched'])
        self.assertFalse(mismatch['displayRegistryMatched'])

    def test_bettergi_reported_game_size_uses_last_capture_window(self):
        text = ('遮罩窗口已启动，游戏大小2560x1440，素材缩放1.00\n'
                '遮罩窗口已启动，游戏大小1920x1080，素材缩放1.00\n')
        self.assertEqual(wf.observed_bgi_game_size(text), {'width': 1920, 'height': 1080})
        self.assertIsNone(wf.observed_bgi_game_size('尚未初始化截图器'))

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

    def test_wrong_runtime_window_size_stops_before_daily_tasks(self):
        outer = self

        class WrongSizeHost(FakeHost):
            def launch(self, exe, name):
                self.launched = True
                self.process = FakeProcess(stuck=True)
                (exe.parent / 'log/new.log').write_text(
                    f'参数指定的一条龙配置：{name}\n'
                    '遮罩窗口已启动，游戏大小2560x1440，素材缩放1.00\n',
                    encoding='utf-8')
                return self.process

        display = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        self.cfg.update(gameDisplaySettings=display,
                        verifyAutomationGraphicsAfterStart=True,
                        restoreManualGraphicsAfterRun=False)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        verified = {
            'compatibleProfileMatched': None, 'qualityMatched': None,
            'displayRegistryMatched': True, 'displayRegistry': display,
            'allMatched': True, 'checkedAt': '2026-09-12T12:00:00+00:00'}
        with (patch.object(wf, 'ensure_genshin_display_settings',
                           return_value={'changed': True}),
              patch.object(wf, 'verify_genshin_automation_graphics',
                           return_value=verified)):
            code, result = self.run_flow(host=WrongSizeHost(outer.root))

        self.assertEqual(code, 4)
        self.assertEqual(result['executionOutcome'], 'graphics_verification_failed')
        self.assertEqual(result['graphicsVerification']['state'], 'failed')
        self.assertEqual(result['graphicsVerification']['observedWindow'],
                         {'width': 2560, 'height': 1440})
        self.assertIn('已停止本次自动化并保留诊断证据', ' '.join(result['errors']))

    def test_runtime_graphics_change_is_guarded_only_while_game_is_alive(self):
        display = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        self.cfg.update(checkpointOnly=False, resumeVerifiedTasks=False,
                        gameDisplaySettings=display, verifyAutomationGraphicsAfterStart=True,
                        restoreManualGraphicsAfterRun=False)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        for closes_game, finishes_flow in ((True, False), (False, False), (False, True)):
            with self.subTest(closes_game=closes_game, finishes_flow=finishes_flow):
                class ClosingHost(FakeHost):
                    sleep_count = 0
                    game_alive = True

                    def processes(self, names):
                        if self.launched and 'GenshinImpact' in names:
                            return [888] if self.game_alive else []
                        return []

                    def launch(self, exe, name):
                        host = self
                        class FinishingProcess(FakeProcess):
                            def poll(self):
                                if host.sleep_count >= 3:
                                    self.returncode = 0
                                return self.returncode
                        super().launch(exe, name)
                        self.process = FinishingProcess(stuck=True)
                        path = exe.parent / 'log/new.log'
                        self.graphics_log = exe.parent / 'log' / ('graphics-' + uuid4().hex + '.log')
                        self.graphics_log.write_text(path.read_text(encoding='utf-8').replace('一条龙和配置组任务结束\n', '') +
                            '遮罩窗口已启动，游戏大小1920x1080，素材缩放1.00\n', encoding='utf-8')
                        return self.process

                    def advance(self, _):
                        self.sleep_count += 1
                        if finishes_flow and self.sleep_count == 1:
                            with self.graphics_log.open('a', encoding='utf-8') as log:
                                log.write('一条龙和配置组任务结束\n')
                        if closes_game or (finishes_flow and self.sleep_count >= 2):
                            self.game_alive = False

                host = ClosingHost(self.root)
                with (patch.object(wf, 'ensure_genshin_display_settings', return_value={}),
                      patch.object(wf, 'verify_genshin_automation_graphics',
                          side_effect=lambda **_: {'allMatched': host.sleep_count == 0}) as verify,
                      patch.object(wf.time, 'monotonic', side_effect=lambda: host.sleep_count * 6.0),
                      patch.object(wf.time, 'sleep', side_effect=host.advance)):
                    _, result = self.run_flow(host=host)
                if closes_game or finishes_flow:
                    self.assertEqual(result['executionOutcome'], 'exited')
                    self.assertEqual(result['graphicsVerification']['state'], 'passed')
                    self.assertEqual(verify.call_count, 2)  # preflight and one live-game check
                else:
                    self.assertEqual(result['executionOutcome'], 'graphics_verification_failed')
                    self.assertEqual(result['graphicsVerification']['state'], 'failed')
                    self.assertEqual(verify.call_count, 3)

    def test_graphics_check_exits_successfully_without_running_daily_tasks(self):
        outer = self

        class CorrectSizeHost(FakeHost):
            def launch(self, exe, name):
                self.launched = True
                self.process = FakeProcess(stuck=True)
                (exe.parent / 'log/new.log').write_text(
                    f'参数指定的一条龙配置：{name}\n'
                    '遮罩窗口已启动，游戏大小1920x1080，素材缩放1.00\n',
                    encoding='utf-8')
                return self.process

        display = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        self.cfg.update(gameDisplaySettings=display,
                        verifyAutomationGraphicsAfterStart=True,
                        restoreManualGraphicsAfterRun=False)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        verified = {
            'compatibleProfileMatched': None, 'qualityMatched': None,
            'displayRegistryMatched': True, 'displayRegistry': display,
            'allMatched': True, 'checkedAt': '2026-09-12T12:00:00+00:00'}
        with (patch.object(wf, 'ensure_genshin_display_settings',
                           return_value={'changed': True}),
              patch.object(wf, 'verify_genshin_automation_graphics',
                           return_value=verified)):
            code, result = self.run_flow(
                host=CorrectSizeHost(outer.root), task=None, graphics_check=True)

        self.assertEqual(code, 0)
        self.assertEqual(result['mode'], 'graphics-check')
        self.assertEqual(result['executionOutcome'], 'graphics_check_passed')
        self.assertEqual(result['outcome'], 'completed')
        self.assertEqual(result['expectedTasks'], [])
        self.assertEqual(result['tasks'], [])

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

    def test_native_startup_failure_stops_promptly_without_confirming_or_replaying_tasks(self):
        host = StartupFailureFakeHost(self.root)
        with (patch.object(wf.time, 'monotonic', side_effect=[0, 0.1]),
              patch.object(wf.time, 'sleep', side_effect=AssertionError('must stop before polling again'))):
            code, result = self.run_flow(host=host)

        self.assertEqual(code, 8)
        self.assertEqual(result['executionOutcome'], 'startup_verification_failed')
        self.assertEqual(result['outcome'], 'unknown')
        self.assertEqual(host.stopped, [987654])
        self.assertEqual(host.stopped_game_pids, [888])
        self.assertFalse(result['gameStillRunning'])
        self.assertEqual(result['tasks'][0]['status'], 'unknown')
        self.assertEqual(result['performance']['tasks'][0]['elapsedSec'], None)
        self.assertEqual(result['rewards'], {})
        self.assertEqual(result['resinEvents'], [])
        self.assertEqual(result['startupFailure']['configName'],
                         wf.read_json(result['runtimeConfig'])['Name'])
        self.assertEqual(result['startupFailure']['bettergiPid'], 987654)
        self.assertEqual(result['startupFailure']['evidenceScope'], 'startup-block-only')
        self.assertEqual(self.base_path.read_bytes(), self.before)
        self.assertIsNone(wf.prior_success(self.root, result['gameDate'], ['合成树脂']))
        context = wf.read_json(Path(result['resultPath']).parent / 'agent-context.json')
        self.assertEqual(context['startupFailure'], result['startupFailure'])

    def test_native_startup_failure_restores_manual_graphics_after_owned_processes_stop(self):
        profile_path = self.root / 'config/genshin-compat-profile.json'
        profile_path.write_bytes((ROOT / 'config/genshin-compat-profile.json').read_bytes())
        self.cfg.update(gameGraphicsProfile='config/genshin-compat-profile.json',
                        gameGraphicsQualityLevel=None, restoreManualGraphicsAfterRun=True)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        snapshot = wf.make_genshin_graphics_snapshot(
            json.dumps({'graphicsData': '{}', 'globalPerfData': '{}'}).encode() + b'\0')
        host = StartupFailureFakeHost(self.root)

        def restore_after_stop(actual_snapshot):
            self.assertEqual(actual_snapshot, snapshot)
            self.assertEqual(host.stopped, [987654])
            self.assertEqual(host.stopped_game_pids, [888])
            return {'restored': True, 'restoredAt': '2026-09-12T12:01:00+00:00',
                    'changedGeneralFields': ['graphicsData'], 'changedRegistryValues': []}

        with (patch.object(wf, 'snapshot_genshin_graphics_settings', return_value=snapshot),
              patch.object(wf, 'ensure_genshin_graphics_profile', return_value={'changed': True}),
              patch.object(wf, 'verify_genshin_automation_graphics', return_value={'allMatched': True}),
              patch.object(wf, 'restore_genshin_graphics_settings', side_effect=restore_after_stop) as restore):
            code, result = self.run_flow(host=host)

        self.assertEqual(code, 8)
        self.assertEqual(result['outcome'], 'unknown')
        restore.assert_called_once_with(snapshot)
        self.assertTrue(result['graphicsIsolation']['restored'])
        self.assertEqual(wf.read_json(
            self.root / 'state/graphics-profile-lease.json')['state'], 'restored')

    def test_final_game_state_is_resampled_after_graphics_cleanup(self):
        profile_path = self.root / 'config/genshin-compat-profile.json'
        profile_path.write_bytes((ROOT / 'config/genshin-compat-profile.json').read_bytes())
        self.cfg.update(gameGraphicsProfile='config/genshin-compat-profile.json',
                        gameGraphicsQualityLevel=None, restoreManualGraphicsAfterRun=True)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        snapshot = wf.make_genshin_graphics_snapshot(
            json.dumps({'graphicsData': '{}', 'globalPerfData': '{}'}).encode() + b'\0')

        class DelayedExitHost(StartupFailureFakeHost):
            pending_exit_observations = 0

            def stop_pids(self, pids):
                result = super().stop_pids(pids)
                if 888 in pids:
                    self.pending_exit_observations = 1
                return result

            def processes(self, names):
                if 'GenshinImpact' in names and self.pending_exit_observations:
                    self.pending_exit_observations -= 1
                    return [888]
                return super().processes(names)

        host = DelayedExitHost(self.root)
        with (patch.object(wf, 'snapshot_genshin_graphics_settings', return_value=snapshot),
              patch.object(wf, 'ensure_genshin_graphics_profile', return_value={'changed': True}),
              patch.object(wf, 'verify_genshin_automation_graphics', return_value={'allMatched': True}),
              patch.object(wf, 'restore_genshin_graphics_settings',
                           return_value={'restored': True, 'restoredAt': '2026-09-12T12:01:00+00:00'})):
            code, result = self.run_flow(host=host)

        self.assertEqual(code, 8)
        self.assertEqual(result['outcome'], 'unknown')
        self.assertTrue(result['graphicsIsolation']['restored'])
        self.assertFalse(result['gameStillRunning'])
        self.assertFalse(wf.read_json(Path(result['resultPath']))['gameStillRunning'])

    def test_native_startup_error_requires_exact_owned_record_and_current_configuration(self):
        name, pid = 'AutoGame_test', 987654
        current = native_startup_log(name, pid)
        expected_text = '一条龙启动核验失败，未执行任务节点'
        for invalid in (
                native_startup_log('AutoGame_other', pid),
                native_startup_log(name, 111),
                current.replace('[ERR]', '[INF]'),
                current.replace('Pages.OneDragonFlowViewModel', 'Pages.OcrScanViewModel'),
                current.replace(expected_text, 'OCR识别文字：' + expected_text),
                current.replace(expected_text, '其他异常\n' + expected_text),
                expected_text,
                f'参数指定的一条龙配置：{name}\n' + expected_text,
                current[current.index('[12:04:00.000]'):],
                current.replace('[12:04:00.000]', '[12:03:00.000] [INF] '
                                f'[Primary:S4:P{pid}:T123456] '
                                'BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel\n'
                                '启用一条龙配置：AutoGame_other\n\n[12:04:00.000]'),
                current.replace(expected_text, '启动核验失败')):
            with self.subTest(log=invalid):
                self.assertIsNone(wf.startup_failure_evidence(invalid, name, pid))
        evidence = wf.startup_failure_evidence(current, name, pid)
        self.assertEqual(evidence['text'], expected_text)
        self.assertLess(evidence['configLine'], evidence['line'])
        self.assertEqual(current.splitlines()[evidence['line'] - 1], expected_text)
        group = native_startup_log(name, pid, failure='配置组 "CurrentGroup" 启动核验失败，未执行任务节点')
        self.assertIsNotNone(wf.startup_failure_evidence(group, name, pid))

    def test_native_startup_error_from_history_or_foreign_pid_is_not_attributed(self):
        name, pid = 'AutoGame_test', 987654
        directory = self.root / 'BetterGI/log'
        path = directory / 'sample.log'
        path.write_text(native_startup_log(name, pid), encoding='utf-8')
        offsets = wf.log_offsets(directory)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(native_startup_log(name, 111))
        text, warnings = wf.collect_log(directory, offsets, pid)
        self.assertEqual(warnings, [])
        self.assertIsNone(wf.startup_failure_evidence(text, name, pid))

    def test_native_startup_error_stops_child_session_only(self):
        self.cfg['executionMode'] = 'childSession'
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)

        class StartupChildHost(ChildSessionFakeHost):
            def launch_child_session(self, exe, name, bettergi_names, timeout_sec=180):
                process, metadata = super().launch_child_session(
                    exe, name, bettergi_names, timeout_sec)
                process.stuck = True
                (exe.parent / 'log/new.log').write_text(
                    native_startup_log(name, process.pid), encoding='utf-8')
                return process, metadata

        host = StartupChildHost(self.root)
        code, result = self.run_flow(host=host)
        self.assertEqual(code, 8)
        self.assertEqual(result['executionOutcome'], 'startup_verification_failed')
        self.assertEqual(host.stopped, [host.CHILD_PID])
        self.assertEqual(host.stopped_game_pids, [host.GAME_PID])
        self.assertNotIn(host.ROOT_PID, host.stopped)
        self.assertNotIn(host.ROOT_PID, host.stopped_game_pids)

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
        self.assertNotIn(host.ROOT_PID, host.stopped_game_pids)
        self.assertNotIn('bettergiPidsClosed', result)

    def test_child_session_mode_kills_root_when_configured(self):
        self.cfg['executionMode'] = 'childSession'
        self.cfg['killBettergiAfterDone'] = True
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        host = ChildSessionFakeHost(self.root)

        code, result = self.run_flow(host=host)

        self.assertNotEqual(code, 0)
        self.assertTrue(host.launched)
        self.assertEqual(result['executionMode'], 'childSession')
        self.assertEqual(result['bettergiPid'], host.CHILD_PID)
        self.assertEqual(result['rootBettergiPid'], host.ROOT_PID)
        self.assertIn(host.ROOT_PID, host.stopped_game_pids)
        self.assertIn(host.ROOT_PID, result.get('bettergiPidsClosed', []))

    def test_foreground_mode_kills_bettergi_when_configured(self):
        self.cfg['executionMode'] = 'foreground'
        self.cfg['killBettergiAfterDone'] = True
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        host = FakeHost(self.root)

        code, result = self.run_flow(host=host)

        self.assertTrue(host.launched)
        self.assertIn(host.process.pid, result.get('bettergiPidsClosed', []))

    def test_child_session_classification_ignores_existing_root_command_forwarder(self):
        roots, children, others = wf.classify_bettergi_session_processes(
            {700001: 5, 700003: 5, 700002: 9}, 5, 9, ignored_pids=[700003])
        self.assertEqual(roots, [700001])
        self.assertEqual(children, [700002])
        self.assertEqual(others, [])

        roots, children, others = wf.classify_bettergi_session_processes(
            {700003: 5, 700002: 9}, 5, 9)
        self.assertEqual(roots, [700003])
        self.assertEqual(children, [700002])
        self.assertEqual(others, [])

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

    def test_full_workflow_resume_skips_same_day_verified_task(self):
        wf.atomic_json(self.root / 'logs/runs/previous/result.json', {
            'runId': 'previous', 'gameDate': '2026-09-12', 'outcome': 'partial',
            'mode': 'daily', 'tasks': [
                {'name': '领取邮件', 'status': 'success'},
                {'name': '合成树脂', 'status': 'success'},
                {'name': '自动秘境', 'status': 'unknown'},
            ]})
        self.cfg.update(defaultProfile='core', resumeVerifiedTasks=True)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        args = argparse.Namespace(
            root=str(self.root), dry_run=True, task=None, profile='core',
            timeout_minutes=1, no_delay=True, allow_repeat=False,
            keep_game=False, allow_existing_game=False, graphics_check=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(wf, 'datetime', FixedClock):
            code = wf.execute(args, FakeHost(self.root, admin=False))
        result = wf.read_json(json.loads(output.getvalue())['resultPath'])

        self.assertEqual(code, 0)
        self.assertEqual(result['expectedTasks'], ['自动秘境', '领取每日奖励'])
        self.assertEqual(result['resumedVerifiedTasks'], [
            {'name': '领取邮件', 'runId': 'previous'},
            {'name': '合成树脂', 'runId': 'previous'}])
        generated = wf.read_json(result['plannedConfig'])
        enabled_names = {
            generated['TaskDefinitions'][task_id]
            for task_id, enabled in generated['TaskEnabledList'].items() if enabled}
        self.assertEqual(enabled_names, {'自动秘境', '领取每日奖励'})

    def test_profile_completion_combines_only_task_status_and_run_provenance(self):
        result = wf.build_profile_completion(
            ['合成树脂', '自动秘境', '领取每日奖励'],
            [{'name': '领取每日奖励', 'status': 'success',
              'evidence': [{'text': 'private reward details'}]}],
            [{'name': '合成树脂', 'runId': 'craft-run'},
             {'name': '自动秘境', 'runId': 'domain-run'}],
            'daily-run')

        self.assertEqual(result['status'], 'completed')
        self.assertEqual([row['runId'] for row in result['tasks']],
                         ['craft-run', 'domain-run', 'daily-run'])
        self.assertNotIn('private reward details', json.dumps(result))

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

    def test_exact_existing_game_can_continue_pending_graphics_lease_after_full_readback(self):
        class AdoptedHost(FakeHost):
            def processes(self, names):
                return [555] if 'GenshinImpact' in names else []

        display = {'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0}
        self.cfg.update(gameGraphicsProfile='config/fake-graphics.json', gameDisplaySettings=display,
                        graceAfterGameClosedSec=0)
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        snapshot_path = self.root / 'logs/runs/original/manual-graphics.json'
        wf.atomic_json(snapshot_path, {'originalManualGraphics': 'retained'})
        snapshot_before = snapshot_path.read_bytes()
        lease = {'schemaVersion': 1, 'runId': 'original', 'state': 'pendingGameExit',
                 'snapshotPath': 'logs/runs/original/manual-graphics.json', 'gamePids': [555]}
        wf.atomic_json(wf._graphics_lease_path(self.root), lease)
        with (patch.object(wf, 'verify_genshin_automation_graphics', return_value={'allMatched': True}) as verify,
              patch.object(wf, 'observed_game_client_size', return_value={'width': 1920, 'height': 1080}) as client,
              patch.object(wf, 'begin_graphics_lease', side_effect=AssertionError('must preserve original snapshot')),
              patch.object(wf, 'restore_genshin_graphics_settings', side_effect=AssertionError('cannot restore running game'))):
            _, result = self.run_flow(host=AdoptedHost(self.root), task='领取邮件', keep_game=True, allow_existing_game=True)
        self.assertEqual(result['adoptedGamePid'], 555)
        verify.assert_called_once()
        client.assert_called_once_with(555)
        self.assertEqual(result['graphicsVerification']['state'], 'passed')
        self.assertEqual(wf.read_json(wf._graphics_lease_path(self.root))['runId'], 'original')
        self.assertEqual(snapshot_path.read_bytes(), snapshot_before)

    def test_pending_graphics_lease_cannot_continue_wrong_session_or_wrong_client_size(self):
        class AdoptedHost(FakeHost):
            def processes(self, names):
                return [555] if 'GenshinImpact' in names else []

        self.cfg.update(gameGraphicsProfile='config/fake-graphics.json',
                        gameDisplaySettings={'width': 1920, 'height': 1080, 'windowed': True, 'monitor': 0})
        wf.atomic_json(self.root / 'config/settings.json', self.cfg)
        wf.atomic_json(self.root / 'logs/runs/original/manual-graphics.json', {'original': 'retained'})
        for prior_pid in (556, 555):
            lease = {'schemaVersion': 1, 'runId': 'original', 'state': 'pendingGameExit',
                'snapshotPath': 'logs/runs/original/manual-graphics.json', 'gamePids': [prior_pid]}
            wf.atomic_json(wf._graphics_lease_path(self.root), lease)
            host = AdoptedHost(self.root)
            with (patch.object(wf, 'verify_genshin_automation_graphics', return_value={'allMatched': True}),
                  patch.object(wf, 'observed_game_client_size', return_value={'width': 2560, 'height': 1440}),
                  patch.object(wf, 'restore_genshin_graphics_settings', side_effect=AssertionError('cannot restore running game'))):
                code, _ = self.run_flow(host=host, task='领取邮件', keep_game=True, allow_existing_game=True)
            self.assertEqual(code, 6)
            self.assertFalse(host.launched)
            self.assertEqual(wf.read_json(wf._graphics_lease_path(self.root)), lease)

    def test_physical_client_size_query_restores_thread_dpi_context_even_when_enumeration_fails(self):
        for enumeration_ok in (True, False):
            user32 = MagicMock()
            context = [123]
            calls = []

            def set_dpi(value):
                value = getattr(value, 'value', value)
                calls.append(value)
                previous, context[0] = context[0], value
                return previous

            def get_owner(hwnd, pointer):
                pointer._obj.value = 555
                return 1

            def get_rectangle(hwnd, pointer):
                pointer._obj.right = 1920 if context[0] == wf.ctypes.c_void_p(-4).value else 1536
                pointer._obj.bottom = 1080 if context[0] == wf.ctypes.c_void_p(-4).value else 864
                return True

            user32.SetThreadDpiAwarenessContext.side_effect = set_dpi
            user32.GetWindowThreadProcessId.side_effect = get_owner
            user32.GetClientRect.side_effect = get_rectangle
            user32.IsWindowVisible.return_value = True
            user32.IsIconic.return_value = False
            user32.EnumWindows.side_effect = lambda callback, _: bool(callback(123, 0)) if enumeration_ok else False
            callback_factory = getattr(wf.ctypes, 'WINFUNCTYPE', wf.ctypes.CFUNCTYPE)
            with (patch.object(wf.ctypes, 'WinDLL', return_value=user32, create=True),
                  patch.object(wf.ctypes, 'WINFUNCTYPE', callback_factory, create=True), patch.object(wf.os, 'name', 'nt')):
                if enumeration_ok:
                    self.assertEqual(wf.observed_game_client_size(555), {'width': 1920, 'height': 1080})
                else:
                    with self.assertRaises(wf.WorkflowError):
                        wf.observed_game_client_size(555)
            self.assertEqual(calls, [wf.ctypes.c_void_p(-4).value, 123])
            self.assertEqual(context[0], 123)

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

    def test_core_profile_includes_mail_and_omits_other_extras_without_modifying_base(self):
        template = wf.read_json(self.base_path)
        selected, names = wf.task_selection(template, profile='core')
        self.assertEqual(names, ['领取邮件', '合成树脂', '自动秘境', '领取每日奖励'])
        self.assertEqual(self.base_path.read_bytes(), self.before)
        self.assertEqual(len(selected), 4)
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

    def test_hoyolab_checkin_integration_dry_run_and_warning(self):
        wf.atomic_json(self.root / 'config/hoyolab.json', {
            'enabled': True, 'cookie': 'ltuid_v2=888888; ltoken_v2=secret',
        })
        info_resp = {
            'retcode': 0, 'message': 'OK',
            'data': {'is_sign': True, 'total_sign_day': 10, 'today': '2026-09-16'}
        }
        with patch('checkin_hoyolab.fetch_checkin_info', return_value=(info_resp, None)):
            code, result = self.run_flow(dry=True)
        self.assertEqual(code, 0)
        self.assertEqual(result['hoyolabCheckin']['status'], 'planned')
        self.assertEqual(result['hoyolabCheckin']['account'], '88***88')
        self.assertTrue(result['hoyolabCheckin']['signedToday'])
        self.assertEqual(result['hoyolabCheckin']['totalSignDays'], 10)


    def test_unknown_main_ui_wait_cannot_trigger_controller_center_click(self):
        outer = self

        class HotSwitchHost(FakeHost):
            def __init__(self, root):
                super().__init__(root, stuck=True)
                self.hot_switch_calls = []

            def launch(self, exe, name):
                process = super().launch(exe, name)
                (exe.parent / 'log/new.log').write_text(
                    '[12:00:01.000] [INF]\n当前不在游戏主界面，等待进入主界面后执行任务...\n',
                    encoding='utf-8')
                return process

            def hot_switch_game_input(self, game_pids):
                self.hot_switch_calls.append(list(game_pids))
                current = wf.read_json(outer.root / 'state/current-run.json')
                wf.atomic_json(outer.root / 'logs/runs' / current['runId'] / 'stop-request.json', {'stop': True})
                return True

        host = HotSwitchHost(self.root)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(wf, 'datetime', FixedClock), patch.object(wf.time, 'monotonic', side_effect=[0, 0, 50, 51, 90, 91, 92, 93]):
            code, result = self.run_flow(host=host)

        self.assertEqual(host.hot_switch_calls, [])
        self.assertFalse(any('手柄热切换回键鼠模式' in note for note in result.get('notes', [])))
        self.assertNotEqual(result['outcome'], 'completed')


if __name__ == '__main__':
    unittest.main()
