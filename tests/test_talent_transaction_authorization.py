"""Offline trusted-port fixtures only. No real grant, game, native gate or image claim."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import talent_transaction_authorization as talent
from scripts.workflow import RunLock


class TalentAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='talent-auth-offline-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 1_800_000_000_000
        self.clock = patch.object(talent, '_now_ms', side_effect=lambda: self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.authority = talent._ReceiptAuthority()
        self.request = talent.TalentStepRequest('run-one', 'step-one', 'Fixture Character', 'normal', 6, 9, 'grant-fixture')
        self.context = talent.GameContext('fixture-existing-machine-nonce', 'fixture-native-account', self.request.run_id,
            'fixture-session', 101, '638500000000000000', 'a' * 64, 'b' * 64, 'fixture-generation', 'c' * 64, self.now)
        self.grant = talent.LocalGrant(self.request.authorization_id, 'd' * 64, self.context.machine_nonce,
            self.context.account_identity, self.now - 1000, self.now + 60_000, talent._day(self.now),
            self.request.character_name, (('normal', 9), ('skill', 9), ('burst', 9)),
            (('Fixture Named Book', 6), ('Fixture Named Material', 4)), 1000)
        self.count = 0
        sources = []
        for kind in ('character', 'talent_entry', 'talent_detail', 'popup', 'mora'):
            sources.extend(self.source(kind, at=self.now - 200 + index * 100) for index in range(2))
        for name in ('Fixture Named Book', 'Fixture Named Material'):
            sources.extend(self.source('material_tooltip', name=name) for _ in range(2))
        self.before = talent.VerifiedBefore(self.request, self.context, 'Fixture Full Talent', 6, 9, True,
            self.now, (talent.MaterialCost('Fixture Named Book', 20, 3),
                       talent.MaterialCost('Fixture Named Material', 10, 2)), 5000, 500, tuple(sources))
        self.holds = talent.AccountResourceHolds(self.context.machine_nonce, self.context.account_identity,
            self.now, (), (self.source('complete_account_journal_enumeration'),))
        self.outcome = None
        self.boundary = talent._TrustedBoundary(self.root, self.context.machine_nonce, b'fixture-key-never-real-' * 2,
            self.authority, lambda _id: self.seal(self.grant), lambda: self.seal(self.context),
            lambda _request, _context: self.seal(self.before), lambda _request, _context: self.seal(self.outcome),
            lambda _context: self.seal(self.holds))
        self.bridge = talent.TalentTransactionAuthorization(self.boundary)

    def seal(self, value):
        return self.authority._seal(value)

    def source(self, kind, *, name='', at=None):
        self.count += 1
        path = self.root / 'logs/offline-fixtures' / ('source-' + str(self.count) + '.bin')
        path.parent.mkdir(parents=True, exist_ok=True)
        data = ('OFFLINE placeholder original ' + str(self.count)).encode()
        path.write_bytes(data)
        return talent.RawSource(path.relative_to(self.root).as_posix(), hashlib.sha256(data).hexdigest(),
            len(data), self.now if at is None else at, self.context.actual_binding_sha256,
            self.context.capture_session, kind, name)

    def blocked(self, function, *args):
        with self.assertRaises((talent.AuthorizationBlocked, ValueError)):
            function(*args)

    def issue(self):
        return self.bridge.issue_permit(self.request)

    def success(self):
        commit = self.now + 100
        after_at = self.now + 200
        world_at = self.now + 300
        after_sources = tuple(self.source(kind, at=after_at) for kind in ('character', 'talent_detail', 'mora'))
        for name in ('Fixture Named Book', 'Fixture Named Material'):
            after_sources += tuple(self.source('named_inventory', name=name, at=after_at) for _ in range(2))
        after = talent.VerifiedAfter(self.before.talent_name, 7, 10, True, after_at,
            (('Fixture Named Book', 17), ('Fixture Named Material', 8)), 4500, after_sources)
        world = talent.VerifiedWorld(world_at, world_at + 100,
            (self.source('world_restore', at=world_at), self.source('world_restore', at=world_at + 100)))
        self.outcome = talent.VerifiedOutcome(self.request, self.context, 'success', after, world, commit,
            (self.source('commit_armed', at=commit),))
        self.now += 500
        return self.outcome

    def no_submission(self):
        first = self.now + 100
        self.outcome = talent.VerifiedOutcome(self.request, self.context, 'no_submission', None,
            talent.VerifiedWorld(first, first + 100,
                (self.source('world_restore', at=first), self.source('world_restore', at=first + 100))),
            None, (self.source('positive_no_submission'),))
        self.now += 300
        return self.outcome

    def next_request(self, *, run='run-two', kind='normal'):
        self.request = replace(self.request, run_id=run, step_id='step-two', talent_type=kind)
        self.context = replace(self.context, run_id=run, observed_at_ms=self.now)
        self.before = replace(self.before, request=self.request, context=self.context, observed_at_ms=self.now,
            sources=tuple(replace(s, observed_at_ms=self.now - 200 + index * 5) for index, s in enumerate(self.before.sources)))
        self.holds = replace(self.holds, observed_at_ms=self.now,
            ledger_sources=tuple(replace(s, observed_at_ms=self.now) for s in self.holds.ledger_sources))

    def test_exact_named_reservation_is_durable_and_not_native_admission(self):
        permit = self.issue()
        self.assertEqual(permit.material_reservation, (('Fixture Named Book', 3), ('Fixture Named Material', 2)))
        self.assertEqual(permit.mora_reservation, 500)
        self.assertFalse(permit.native_consumption_enabled)
        self.assertEqual(self.bridge.assert_still_valid(permit), permit)
        path = self.bridge._permits[id(permit)][1] / 'reservation.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), permit.reservation_sha256)
        with self.assertRaises(NotImplementedError):
            self.bridge.native_admission(permit)

    def test_public_dict_and_approval_boolean_cannot_issue(self):
        self.blocked(self.bridge.issue_permit, {'approval': True, 'request': self.request})
        self.blocked(talent.TalentTransactionAuthorization, {'approval': True})

    def test_typed_dataclass_without_registered_receipt_is_not_authentication(self):
        self.bridge = talent.TalentTransactionAuthorization(replace(self.boundary, read_grant=lambda _: self.grant))
        self.blocked(self.issue)

    def test_foreign_receipt_authority_is_rejected(self):
        forged = talent._ReceiptAuthority()._seal(self.grant)
        self.bridge = talent.TalentTransactionAuthorization(replace(self.boundary, read_grant=lambda _: forged))
        self.blocked(self.issue)

    def test_authenticated_receipt_mutation_is_detected(self):
        receipt = self.seal(self.grant)
        object.__setattr__(self.grant, 'mora_cap', 90000)
        self.bridge = talent.TalentTransactionAuthorization(replace(self.boundary, read_grant=lambda _: receipt))
        self.blocked(self.issue)

    def test_existing_protected_key_is_required(self):
        self.blocked(talent.TalentTransactionAuthorization, replace(self.boundary, ledger_key=b''))

    def test_actual_expired_original_grant_is_rejected(self):
        self.grant = replace(self.grant, expires_at_ms=self.now)
        self.blocked(self.issue)
        self.assertFalse((self.root / 'state/talent-transaction-ledger').exists())

    def test_not_yet_approved_grant_is_rejected(self):
        self.grant = replace(self.grant, approved_at_ms=self.now + 1)
        self.blocked(self.issue)

    def test_game_day_cannot_be_renewed_by_request(self):
        self.grant = replace(self.grant, game_day=talent._day(self.now) - 1)
        self.blocked(self.issue)

    def test_wrong_account_or_machine_grant_is_rejected(self):
        for change in ({'account_identity': 'different-account'}, {'machine_nonce': 'different-machine'}):
            with self.subTest(change=change):
                old = self.grant; self.grant = replace(old, **change)
                self.blocked(self.issue); self.grant = old

    def test_wrong_target_character_or_talent_ceiling_is_rejected(self):
        for change in ({'character_name': 'different-character'},
                       {'talent_targets': (('normal', 8), ('skill', 9), ('burst', 9))}):
            with self.subTest(change=change):
                old = self.grant; self.grant = replace(old, **change)
                self.blocked(self.issue); self.grant = old

    def test_all_three_talents_are_parameterized(self):
        for kind in ('normal', 'skill', 'burst'):
            with self.subTest(kind=kind):
                # Each fixture has a separate isolated trusted install, not separate scope on one account.
                other = TalentAuthorizationTests(); other.setUp()
                try:
                    other.request = replace(other.request, talent_type=kind)
                    other.before = replace(other.before, request=other.request)
                    self.assertEqual(other.issue().request.talent_type, kind)
                finally:
                    other.doCleanups()

    def test_no_crown_ten_or_unknown_talent(self):
        for change in ({'target_base_level': 10}, {'talent_type': 'unknown'}, {'expected_base_level': True},
                       {'run_id': '../escape'}):
            self.blocked(self.bridge.issue_permit, replace(self.request, **change))

    def test_context_needs_real_current_binding_and_exact_tick_string(self):
        for change in ({'observed_at_ms': self.now - 1501}, {'process_started_utc_ticks': 638500000000000000},
                       {'run_id': 'other-run'}, {'machine_nonce': 'other-machine'}):
            with self.subTest(change=change):
                old = self.context; self.context = replace(old, **change)
                self.blocked(self.issue); self.context = old

    def test_complete_account_unknown_blocks_new_grant(self):
        self.holds = replace(self.holds, unresolved_transaction_ids=('fixture-old-artifact-unknown',))
        self.blocked(self.issue)

    def test_raw_empty_hold_list_cannot_authenticate(self):
        self.bridge = talent.TalentTransactionAuthorization(replace(self.boundary, read_account_holds=lambda _: []))
        self.blocked(self.issue)

    def test_before_identity_or_full_title_or_plus_three_must_match(self):
        for change in ({'base_level': 5}, {'talent_name': ''}, {'display_level': 6}, {'fixed_plus_three': 1}):
            with self.subTest(change=change):
                old = self.before; self.before = replace(old, **change)
                self.blocked(self.issue); self.before = old

    def test_before_stale_or_incomplete_source_categories_rejected(self):
        for change in ({'observed_at_ms': self.now - 1501},
                       {'sources': tuple(s for s in self.before.sources if s.kind != 'popup')}):
            with self.subTest(change=change):
                old = self.before; self.before = replace(old, **change)
                self.blocked(self.issue); self.before = old

    def test_named_material_pair_required(self):
        self.before = replace(self.before, sources=tuple(s for s in self.before.sources
            if not (s.kind == 'material_tooltip' and s.name == 'Fixture Named Material')))
        self.blocked(self.issue)

    def test_original_source_tamper_or_binding_replacement_rejected(self):
        source = self.before.sources[0]
        (self.root / source.relative_path).write_bytes(b'changed original')
        self.blocked(self.issue)

    def test_original_source_path_escape_rejected(self):
        self.before = replace(self.before, sources=(replace(self.before.sources[0], relative_path='../outside'), *self.before.sources[1:]))
        self.blocked(self.issue)

    def test_exact_named_caps_not_total_substitute(self):
        self.grant = replace(self.grant, material_caps=(('Fixture Named Book', 1000), ('Fixture Named Material', 1)))
        self.blocked(self.issue)

    def test_duplicate_forbidden_negative_bool_or_zero_route_cost_rejected(self):
        for materials in ((self.before.materials[0], self.before.materials[0]),
                          (talent.MaterialCost('原石', 100, 1),),
                          (talent.MaterialCost('Fixture Named Book', 3, 3),),
                          (talent.MaterialCost('Fixture Named Book', 100, True),),
                          (talent.MaterialCost('Fixture Named Book', 100, -1),)):
            with self.subTest(materials=materials):
                old = self.before; self.before = replace(old, materials=materials)
                self.blocked(self.issue); self.before = old

    def test_zero_mora_after_route_or_insufficient_mora_budget_rejected(self):
        self.before = replace(self.before, mora_owned=500)
        self.blocked(self.issue)
        self.before = replace(self.before, mora_owned=5000)
        self.grant = replace(self.grant, mora_cap=499)
        self.blocked(self.issue)

    def test_same_step_is_never_replayed_even_with_different_bridge(self):
        self.issue()
        self.bridge = talent.TalentTransactionAuthorization(self.boundary)
        self.blocked(self.issue)

    def test_pending_reservation_blocks_every_new_run_and_grant(self):
        self.issue(); self.next_request()
        self.grant = replace(self.grant, authorization_id='new-grant')
        self.request = replace(self.request, authorization_id='new-grant')
        self.before = replace(self.before, request=self.request)
        self.bridge = talent.TalentTransactionAuthorization(self.boundary)
        self.blocked(self.issue)

    def test_unknown_outcome_keeps_full_reservation(self):
        permit = self.issue(); self.no_submission()
        self.outcome = replace(self.outcome, kind='unknown')
        self.blocked(self.bridge.finalize, permit)
        step = self.bridge._permits[id(permit)][1]
        self.assertEqual({p.name for p in step.iterdir()}, {'reservation.json'})
        self.next_request(); self.blocked(self.issue)

    def test_exact_success_finalizes_only_once_and_charges_original_caps(self):
        permit = self.issue(); self.success()
        self.assertEqual(self.bridge.finalize(permit), 'success')
        self.blocked(self.bridge.finalize, permit)
        self.next_request(); self.bridge = talent.TalentTransactionAuthorization(self.boundary)
        second = self.issue(); self.success()
        self.assertEqual(self.bridge.finalize(second), 'success')
        self.next_request(run='run-three'); self.blocked(self.issue)

    def test_positive_no_submission_plus_world_releases_only_its_reservation(self):
        permit = self.issue(); self.no_submission()
        self.assertEqual(self.bridge.finalize(permit), 'no_submission')
        self.next_request(); self.assertEqual(self.issue().mora_reservation, 500)

    def test_no_submission_without_positive_input_boundary_is_blocked(self):
        permit = self.issue(); self.no_submission()
        self.outcome = replace(self.outcome, submission_sources=(replace(self.outcome.submission_sources[0], kind='absence_of_events'),))
        self.blocked(self.bridge.finalize, permit)

    def test_no_submission_cannot_release_a_submitted_receipt(self):
        permit = self.issue(); self.success()
        self.outcome = replace(self.outcome, kind='no_submission')
        self.blocked(self.bridge.finalize, permit)

    def test_success_needs_independent_exact_base_plus_one(self):
        permit = self.issue(); self.success()
        for level in (6, 8):
            original = self.outcome
            self.outcome = replace(original, after=replace(original.after, base_level=level, display_level=level + 3))
            self.blocked(self.bridge.finalize, permit); self.outcome = original

    def test_success_needs_every_old_named_material_and_exact_mora_delta(self):
        permit = self.issue(); self.success()
        after = self.outcome.after
        for change in ({'material_counts': (('Fixture Named Book', 17),)},
                       {'material_counts': (('Fixture Named Book', 16), ('Fixture Named Material', 8))},
                       {'mora': 4499}):
            original = self.outcome; self.outcome = replace(original, after=replace(after, **change))
            self.blocked(self.bridge.finalize, permit); self.outcome = original

    def test_success_missing_after_original_named_pair_rejected(self):
        permit = self.issue(); self.success()
        after = self.outcome.after
        self.outcome = replace(self.outcome, after=replace(after,
            sources=tuple(s for s in after.sources if s.kind != 'named_inventory')))
        self.blocked(self.bridge.finalize, permit)

    def test_success_requires_native_once_commit_before_original_deadline(self):
        permit = self.issue(); self.success()
        self.outcome = replace(self.outcome, submission_at_ms=permit.expires_at_ms)
        self.blocked(self.bridge.finalize, permit)

    def test_no_world_or_stale_world_retains_reservation(self):
        permit = self.issue(); self.success()
        original = self.outcome
        self.outcome = replace(original, world=None)
        self.blocked(self.bridge.finalize, permit)
        self.outcome = original; self.now += 2000
        self.blocked(self.bridge.finalize, permit)

    def test_fabricated_permit_dataclass_and_cross_restart_permit_rejected(self):
        permit = self.issue()
        self.blocked(self.bridge.assert_still_valid, replace(permit))
        bridge = talent.TalentTransactionAuthorization(self.boundary)
        self.blocked(bridge.assert_still_valid, permit)

    def test_original_grant_changes_or_account_switch_invalidate_permit(self):
        permit = self.issue()
        self.grant = replace(self.grant, mora_cap=2000)
        self.blocked(self.bridge.assert_still_valid, permit)
        self.context = replace(self.context, account_identity='other-account')
        self.blocked(self.bridge.assert_still_valid, permit)

    def test_fresh_binding_timestamp_may_change_but_identity_cannot(self):
        permit = self.issue(); self.now += 500
        self.context = replace(self.context, observed_at_ms=self.now)
        self.assertEqual(self.bridge.assert_still_valid(permit), permit)
        self.context = replace(self.context, backend_generation='restarted')
        self.blocked(self.bridge.assert_still_valid, permit)

    def test_nonce_replacement_cannot_move_account_scope(self):
        self.issue(); self.next_request()
        self.context = replace(self.context, machine_nonce='new-local-nonce')
        self.grant = replace(self.grant, machine_nonce='new-local-nonce')
        self.holds = replace(self.holds, machine_nonce='new-local-nonce')
        self.bridge = talent.TalentTransactionAuthorization(replace(self.boundary, machine_nonce='new-local-nonce'))
        self.blocked(self.issue)

    def test_corrupt_terminal_and_public_json_rehash_cannot_release_unknown(self):
        permit = self.issue(); step = self.bridge._permits[id(permit)][1]
        for name in ('outcome.json', 'terminal.json'):
            (step / name).write_text(json.dumps({'kind': 'no_submission', 'evidenceVerified': True}), encoding='utf-8')
        self.next_request(); self.blocked(self.issue)

    def test_authenticated_terminal_tamper_is_rejected(self):
        permit = self.issue(); self.no_submission(); self.bridge.finalize(permit)
        path = self.bridge._permits[id(permit)][1] / 'terminal.json'
        value = json.loads(path.read_text()); value['payload']['kind'] = 'success'
        path.write_text(json.dumps(value), encoding='utf-8')
        self.next_request(); self.blocked(self.issue)

    def test_partial_create_new_record_blocks_account(self):
        permit = self.issue(); step = self.bridge._permits[id(permit)][1]
        (step / 'reservation.json').write_bytes(b'{')
        self.next_request(); self.blocked(self.issue)

    def test_held_actual_workflow_lock_is_reused(self):
        with RunLock(self.root / 'state/workflow.lock') as held:
            bridge = talent.TalentTransactionAuthorization(replace(self.boundary, existing_run_lock=held))
            self.assertFalse(bridge.issue_permit(self.request).native_consumption_enabled)

    def test_closed_or_wrong_lock_is_rejected(self):
        held = RunLock(self.root / 'state/other.lock')
        bridge = talent.TalentTransactionAuthorization(replace(self.boundary, existing_run_lock=held))
        self.blocked(bridge.issue_permit, self.request)

    def test_prior_finalized_original_source_change_blocks_next_admission(self):
        permit = self.issue(); self.no_submission(); self.bridge.finalize(permit)
        path = self.root / self.outcome.world.sources[0].relative_path
        path.write_bytes(b'modified prior independently verified world')
        self.next_request(); self.blocked(self.issue)

    def test_terminal_write_failure_keeps_account_blocked(self):
        permit = self.issue(); self.no_submission()
        write = self.bridge._write_once
        def fail_terminal(path, value):
            if path.name == 'terminal.json':
                raise OSError('offline injected durable terminal failure')
            return write(path, value)
        with patch.object(self.bridge, '_write_once', side_effect=fail_terminal):
            with self.assertRaises(OSError):
                self.bridge.finalize(permit)
        self.blocked(self.bridge.finalize, permit)
        self.next_request(); self.blocked(self.issue)

    def test_reservation_flush_failure_keeps_partial_directory_blocked(self):
        write = self.bridge._write_once
        def fail_reservation(path, value):
            if path.name == 'reservation.json':
                path.write_bytes(b'{partial offline injected reservation')
                raise OSError('offline injected reservation failure')
            return write(path, value)
        with patch.object(self.bridge, '_write_once', side_effect=fail_reservation):
            with self.assertRaises(OSError):
                self.issue()
        self.next_request(); self.blocked(self.issue)

    def test_expiry_after_reservation_blocks_future_admission_keeps_reservation(self):
        permit = self.issue(); self.now = permit.expires_at_ms
        self.context = replace(self.context, observed_at_ms=self.now)
        self.blocked(self.bridge.assert_still_valid, permit)
        step = self.bridge._permits[id(permit)][1]
        self.assertEqual({p.name for p in step.iterdir()}, {'reservation.json'})

    def test_delayed_accounting_after_expiry_does_not_renew_input_permission(self):
        permit = self.issue(); self.success()
        self.now = permit.expires_at_ms + 500
        self.context = replace(self.context, observed_at_ms=self.now)
        self.outcome = replace(self.outcome, world=talent.VerifiedWorld(self.now - 200, self.now - 100,
            (self.source('world_restore', at=self.now - 200), self.source('world_restore', at=self.now - 100))))
        self.assertEqual(self.bridge.finalize(permit), 'success')
        self.next_request(); self.blocked(self.issue)

    def test_copying_authenticated_prior_records_to_new_directory_is_blocked(self):
        permit = self.issue(); self.no_submission(); self.bridge.finalize(permit)
        step = self.bridge._permits[id(permit)][1]
        copied = step.parent / ('e' * 64)
        copied.mkdir()
        for source in step.iterdir():
            (copied / source.name).write_bytes(source.read_bytes())
        self.next_request(); self.blocked(self.issue)

    def test_final_outcome_actual_account_switch_is_blocked(self):
        permit = self.issue(); self.success()
        self.context = replace(self.context, account_identity='different-live-account', observed_at_ms=self.now)
        self.blocked(self.bridge.finalize, permit)

    def test_boolean_or_float_verified_numeric_values_cannot_pass(self):
        for change in ({'base_level': 6.0}, {'observed_at_ms': float(self.now)}, {'display_level': 9.0}):
            original = self.before; self.before = replace(original, **change)
            self.blocked(self.issue); self.before = original

    def test_accounting_never_extends_original_grant_fingerprint(self):
        permit = self.issue(); self.no_submission(); self.bridge.finalize(permit)
        self.next_request()
        self.grant = replace(self.grant, expires_at_ms=self.grant.expires_at_ms + 60_000)
        self.blocked(self.issue)

    def test_old_preparation_frames_are_allowed_only_with_fresh_final_popup_pair(self):
        self.before = replace(self.before, sources=tuple(replace(s, observed_at_ms=self.now - 4000)
            if s.kind != 'popup' else s for s in self.before.sources))
        self.assertFalse(self.issue().native_consumption_enabled)

    def test_previous_game_day_original_before_sources_are_rejected(self):
        previous_day = self.grant.game_day * 86_400_000 - 4 * 3_600_000 - 1
        self.before = replace(self.before, sources=(replace(self.before.sources[0], observed_at_ms=previous_day), *self.before.sources[1:]))
        self.blocked(self.issue)

    def test_stale_final_popup_pair_is_rejected_even_if_summary_is_fresh(self):
        self.before = replace(self.before, sources=tuple(replace(s, observed_at_ms=self.now - 2000)
            if s.kind == 'popup' else s for s in self.before.sources))
        self.blocked(self.issue)

    def test_final_popup_frames_expiring_during_ledger_io_cannot_create_reservation(self):
        popup_index = 0
        sources = []
        for source in self.before.sources:
            if source.kind == 'popup':
                source = replace(source, observed_at_ms=self.now - 1499 + popup_index)
                popup_index += 1
            sources.append(source)
        self.before = replace(self.before, sources=tuple(sources))
        original_usage = self.bridge._usage
        def slow_ledger_io(account, grant):
            result = original_usage(account, grant)
            self.now += 2
            return result
        with patch.object(self.bridge, '_usage', side_effect=slow_ledger_io):
            self.blocked(self.issue)
        self.assertEqual(self.now - self.before.observed_at_ms, 2)
        self.assertEqual(list((self.root / 'state/talent-transaction-ledger').rglob('reservation.json')), [])


if __name__ == '__main__':
    unittest.main()
