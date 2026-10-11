"""Strict minimum graphics-profile validation without registry access."""
from __future__ import annotations

import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow as wf


class GraphicsProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile = wf.read_json(ROOT / "config/genshin-compat-profile.json")
        self.profile['graphicsData']['volatileVersion'] = 'OSRELWin7.0.0'  # Stable synthetic migration baseline.
        self.general = {"graphicsData": json.dumps({"currentVolatielGrade": 1,
            "customVolatileGrades": [], "volatileVersion": self.profile["graphicsData"]["volatileVersion"]}),
            "globalPerfData": "{}", "gammaValue": 2.2,
            "accountSentinel": {"marker": "anonymous fixture"}}

    def rejected(self, profile):
        raw = json.dumps(self.general).encode("utf-8") + b"\0"
        with self.assertRaises(wf.WorkflowError):
            wf.update_genshin_general_data_profile(raw, profile)

    def test_schema_version_requires_exact_integer_one(self):
        for value in (True, 1.0, "1", None, 2):
            with self.subTest(value=value):
                profile = copy.deepcopy(self.profile)
                profile["schemaVersion"] = value
                self.rejected(profile)

    def test_custom_grade_requires_exact_integer_minus_one(self):
        for value in (-1.0, "-1", True, False, None, 1):
            with self.subTest(value=value):
                profile = copy.deepcopy(self.profile)
                profile["graphicsData"]["currentVolatielGrade"] = value
                self.rejected(profile)

    def test_minimum_values_require_exact_integer_one(self):
        for value in (True, 1.0, "1", None, 0, 2):
            with self.subTest(value=value):
                profile = copy.deepcopy(self.profile)
                profile["graphicsData"]["customVolatileGrades"][0]["value"] = value
                self.rejected(profile)

    def test_valid_minimum_profile_replaces_only_graphics_sections(self):
        raw = json.dumps(self.general).encode("utf-8") + b"\0"
        updated, _ = wf.update_genshin_general_data_profile(raw, self.profile)
        value = json.loads(updated.rstrip(b"\0"))
        self.assertEqual(json.loads(value["graphicsData"]), self.profile["graphicsData"])
        self.assertEqual(json.loads(value["globalPerfData"]), self.profile["globalPerfData"])
        self.assertEqual(value["gammaValue"], 2.2)
        self.assertEqual(value["accountSentinel"], self.general["accountSentinel"])

    def assessment(self, graphics=None, perf=None, extra=None):
        value = {'graphicsData': graphics or copy.deepcopy(self.profile['graphicsData']),
                 'globalPerfData': perf or copy.deepcopy(self.profile['globalPerfData']), **(extra or {})}
        return wf.assess_genshin_automation_graphics(json.dumps(value).encode('utf-8'), profile=self.profile)

    def test_version_migration_retains_strict_guard_and_records_only_actual_diff(self):
        graphics = copy.deepcopy(self.profile['graphicsData'])
        graphics['volatileVersion'] = 'OSRELWin7.1.0'
        result = self.assessment(graphics=graphics)
        self.assertFalse(result['allMatched'])
        self.assertFalse(result['compatibleProfileMatched'])
        self.assertEqual(result['graphicsDiagnostic']['differences'], [{'field': 'graphicsData.volatileVersion',
            'expected': self.profile['graphicsData']['volatileVersion'], 'actual': 'OSRELWin7.1.0'}])
        self.assertEqual(result['graphicsDiagnostic']['actual']['globalPerfData'], self.profile['globalPerfData'])

    def test_grade_or_perf_drift_remains_a_guard_failure(self):
        graphics = copy.deepcopy(self.profile['graphicsData'])
        graphics['customVolatileGrades'][0]['value'] = 2
        result = self.assessment(graphics=graphics)
        self.assertFalse(result['allMatched'])
        self.assertEqual(result['graphicsDiagnostic']['differences'][0]['field'], 'graphicsData.customVolatileGrades[0].value')
        perf = copy.deepcopy(self.profile['globalPerfData'])
        perf['saveItems'][0]['index'] += 1
        result = self.assessment(perf=perf)
        self.assertFalse(result['allMatched'])
        self.assertTrue(any(item['field'].endswith('.index') for item in result['graphicsDiagnostic']['differences']))

    def test_diagnostic_excludes_arbitrary_registry_and_nested_secret_fields(self):
        graphics = copy.deepcopy(self.profile['graphicsData'])
        graphics['accountCookie'] = 'nested-private-fixture'
        graphics['customVolatileGrades'][0]['password'] = 'row-private-fixture'
        perf = copy.deepcopy(self.profile['globalPerfData'])
        perf['accountToken'] = 'perf-private-fixture'
        result = self.assessment(graphics=graphics, perf=perf, extra={'uid': 'root-private-fixture'})
        output = json.dumps(result)
        for secret in ('nested-private-fixture', 'row-private-fixture', 'perf-private-fixture', 'root-private-fixture',
                       'accountCookie', 'password', 'accountToken', 'uid'):
            self.assertNotIn(secret, output)
        self.assertFalse(result['allMatched'])

    def test_offline_snapshot_cli_is_whitelisted_and_does_not_access_registry(self):
        directory = ROOT / 'tests/.artifacts' / ('graphics-diagnostic-' + uuid4().hex[:10])
        directory.mkdir(parents=True)
        graphics = copy.deepcopy(self.profile['graphicsData'])
        graphics['volatileVersion'] = 'OSRELWin7.1.0'
        path = directory / 'fake-snapshot.json'
        profile_path = directory / 'fake-profile.json'
        profile_path.write_text(json.dumps(self.profile), encoding='utf-8')
        path.write_text(json.dumps({'generalDataFields': {'graphicsData': json.dumps(graphics),
            'globalPerfData': json.dumps(self.profile['globalPerfData']), 'cookie': 'excluded-fixture'},
            'account': 'excluded-root-fixture'}), encoding='utf-8')
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = wf.main(['diagnose-graphics', '--snapshot', str(path), '--profile', str(profile_path)])
        self.assertEqual(code, 0)
        self.assertNotIn('excluded', stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())['differences'][0]['field'], 'graphicsData.volatileVersion')

    def migration_evidence(self):
        graphics = copy.deepcopy(self.profile['graphicsData'])
        graphics['volatileVersion'] = 'OSRELWin7.1.0'
        return {'generalDataFields': {'graphicsData': json.dumps(graphics),
                'globalPerfData': json.dumps(self.profile['globalPerfData'])}}

    def test_evidenced_metadata_migration_preserves_all_manual_and_account_fields(self):
        raw = json.dumps(self.general).encode('utf-8') + b'\0'
        updated, summary = wf.update_genshin_graphics_version_metadata(raw, self.profile, self.migration_evidence())
        actual = json.loads(updated.rstrip(b'\0'))
        before_graphics = json.loads(self.general['graphicsData'])
        self.assertEqual(json.loads(actual['graphicsData']), dict(before_graphics, volatileVersion='OSRELWin7.1.0'))
        self.assertEqual({key: value for key, value in actual.items() if key != 'graphicsData'},
                         {key: value for key, value in self.general.items() if key != 'graphicsData'})
        self.assertTrue(summary['changed'])
        repeated, summary = wf.update_genshin_graphics_version_metadata(updated, self.profile, self.migration_evidence())
        self.assertEqual(repeated, updated)
        self.assertFalse(summary['changed'])
        self.assertNotIn('account', json.dumps(summary))

    def test_metadata_migration_rejects_changed_grades_perf_structure_and_foreign_version(self):
        raw = json.dumps(self.general).encode('utf-8') + b'\0'
        for section, field, value in (('graphicsData', 'currentVolatielGrade', 1),
                ('graphicsData', 'newUnverifiedField', 1), ('globalPerfData', 'portedVersion', 'OSRELWin7.1.0')):
            evidence = self.migration_evidence()
            item = json.loads(evidence['generalDataFields'][section])
            item[field] = value
            evidence['generalDataFields'][section] = json.dumps(item)
            with self.assertRaises(wf.WorkflowError):
                wf.update_genshin_graphics_version_metadata(raw, self.profile, evidence)
        changed = copy.deepcopy(self.general)
        graphics = json.loads(changed['graphicsData'])
        graphics['volatileVersion'] = 'OSRELWin8.0.0'
        changed['graphicsData'] = json.dumps(graphics)
        with self.assertRaises(wf.WorkflowError):
            wf.update_genshin_graphics_version_metadata(json.dumps(changed).encode(), self.profile, self.migration_evidence())


if __name__ == "__main__":
    unittest.main()
