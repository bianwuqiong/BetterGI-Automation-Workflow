"""Fail-closed Host talent reservation core. No grant issuer, raw validator or native input.

The private composition seam is deliberately unintegrated. Receipts authenticate object
identity in one process; JSON, dataclass constructors and caller approval flags cannot
authenticate evidence. See docs/TALENT_TRANSACTION_AUTHORIZATION.md before integration.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import unicodedata

try:
    from .workflow import RunLock
except ImportError:
    from workflow import RunLock


class AuthorizationBlocked(ValueError):
    pass


def _fail(reason):
    raise AuthorizationBlocked(reason)


def _now_ms():
    return time.time_ns() // 1_000_000


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _integer(value, low=0, high=2_147_483_647):
    if type(value) is not int or not low <= value <= high:
        _fail('bounded_integer_required')
    return value


def _text(value, maximum=128):
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > maximum or any(unicodedata.category(c) == 'Cc' for c in value)):
        _fail('bounded_exact_text_required')
    return value


def _sha(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        _fail('exact_sha256_required')
    return value


def _day(at):
    # UTC+8 04:00 boundary, identical to Native24 GameDay.
    return (at + 4 * 3_600_000) // 86_400_000


def _plain(path):
    path = Path(path)
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        _fail('trusted_absolute_local_root_required')
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and
                getattr(parent.stat(), 'st_file_attributes', 0) & 0x400):
            _fail('reparse_or_symlink_rejected')
    return path


@dataclass(frozen=True)
class TalentStepRequest:
    run_id: str
    step_id: str
    character_name: str
    talent_type: str
    expected_base_level: int
    target_base_level: int
    authorization_id: str


@dataclass(frozen=True)
class LocalGrant:
    authorization_id: str
    source_sha256: str  # digest only; private authorization wording is never read here
    machine_nonce: str  # existing trusted local install identity, never generated here
    account_identity: str  # actual native account identity; not caller scope
    approved_at_ms: int
    expires_at_ms: int
    game_day: int
    character_name: str
    talent_targets: tuple  # ((normal, ceiling), (skill, ceiling), (burst, ceiling))
    material_caps: tuple  # exact approved named resource ceilings
    mora_cap: int


@dataclass(frozen=True)
class GameContext:
    machine_nonce: str
    account_identity: str
    run_id: str
    capture_session: str
    process_id: int
    process_started_utc_ticks: str
    executable_sha256: str
    native_assembly_sha256: str
    backend_generation: str
    actual_binding_sha256: str
    observed_at_ms: int


@dataclass(frozen=True)
class RawSource:
    relative_path: str
    sha256: str
    length: int
    observed_at_ms: int
    binding_sha256: str
    capture_session: str
    kind: str
    name: str = ''


@dataclass(frozen=True)
class MaterialCost:
    name: str
    owned: int
    required: int


@dataclass(frozen=True)
class VerifiedBefore:
    request: TalentStepRequest
    context: GameContext
    talent_name: str
    base_level: int
    display_level: int
    fixed_plus_three: bool
    observed_at_ms: int
    materials: tuple
    mora_owned: int
    mora_required: int
    sources: tuple


@dataclass(frozen=True)
class VerifiedAfter:
    talent_name: str
    base_level: int
    display_level: int
    fixed_plus_three: bool
    observed_at_ms: int
    material_counts: tuple
    mora: int
    sources: tuple


@dataclass(frozen=True)
class VerifiedWorld:
    first_at_ms: int
    second_at_ms: int
    sources: tuple


@dataclass(frozen=True)
class VerifiedOutcome:
    request: TalentStepRequest
    context: GameContext
    kind: str  # success / no_submission / unknown; independently sealed, never caller status
    after: VerifiedAfter | None
    world: VerifiedWorld | None
    submission_at_ms: int | None
    submission_sources: tuple  # immutable native commit_armed or positive no-input sources


@dataclass(frozen=True)
class AccountResourceHolds:
    machine_nonce: str
    account_identity: str
    observed_at_ms: int
    unresolved_transaction_ids: tuple
    # Complete account-wide enumeration from existing artifact/cultivation/native journals.
    ledger_sources: tuple


@dataclass(frozen=True)
class TalentSpendPermit:
    account_scope: str
    authorization_id: str
    request: TalentStepRequest
    capture_session: str
    game_binding_sha256: str
    expires_at_ms: int
    game_day: int
    material_reservation: tuple
    mora_reservation: int
    reservation_sha256: str
    # This record is only a durable Host reservation, never a native click credential.
    native_consumption_enabled: bool = False


class _Receipt:
    __slots__ = ('_value',)

    def __init__(self, value):
        self._value = value


class _ReceiptAuthority:
    """PRIVATE same-process adapter seam; no JSON parser or public minting endpoint.

    A future reviewed native verifier/local grant reader owns this instance. It calls
    _seal only after independent verification. Offline fixtures emulate this boundary.
    Arbitrary Python code already running in the trusted process is outside this model.
    """
    def __init__(self):
        self._receipts = {}

    def _seal(self, value):
        receipt = _Receipt(value)
        # Retain strong references: object IDs cannot be recycled into authentication.
        self._receipts[id(receipt)] = (receipt, value, _bytes(asdict(value)))
        return receipt

    def _accept(self, receipt, expected_type):
        retained = self._receipts.get(id(receipt))
        if (retained is None or retained[0] is not receipt or type(receipt) is not _Receipt
                or type(retained[1]) is not expected_type or receipt._value is not retained[1]
                or _bytes(asdict(retained[1])) != retained[2]):
            _fail('untrusted_or_mutated_receipt')
        return retained[1]


@dataclass(frozen=True)
class _TrustedBoundary:
    """No production instance exists. Root and every reader are trusted composition only.

    Readers return identity-authenticated _Receipt objects, never JSON/bool attestations.
    existing_run_lock may be the actual currently held workflow.RunLock to avoid nesting.
    """
    private_root: Path
    machine_nonce: str
    ledger_key: bytes  # existing local protected key; never created/persisted by this core
    authority: _ReceiptAuthority
    read_grant: object
    read_context: object
    read_before: object
    read_outcome: object
    read_account_holds: object
    existing_run_lock: object = None


class TalentTransactionAuthorization:
    """Public policy core; caller request has no grant, scope, path, balance or approval."""
    def __init__(self, trusted_boundary):
        if type(trusted_boundary) is not _TrustedBoundary:
            _fail('unintegrated_trusted_host_boundary')
        self._trusted = trusted_boundary
        self._root = _plain(trusted_boundary.private_root)
        _text(trusted_boundary.machine_nonce, 256)
        if type(trusted_boundary.ledger_key) is not bytes or len(trusted_boundary.ledger_key) < 32:
            _fail('existing_protected_local_ledger_key_required')
        if type(trusted_boundary.authority) is not _ReceiptAuthority:
            _fail('trusted_receipt_authority_required')
        self._permits = {}

    @staticmethod
    def _request(request):
        if type(request) is not TalentStepRequest:
            _fail('typed_request_required_no_caller_approval_fields')
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}', request.run_id):
            _fail('bounded_run_required')
        for value in (request.step_id, request.character_name, request.authorization_id):
            _text(value)
        if request.talent_type not in ('normal', 'skill', 'burst'):
            _fail('three_official_talent_types_only')
        _integer(request.expected_base_level, 1, 8)
        _integer(request.target_base_level, 2, 9)
        if request.target_base_level <= request.expected_base_level:
            _fail('target_ceiling_must_exceed_current')

    def _read(self, reader, expected, *args):
        return self._trusted.authority._accept(reader(*args), expected)

    @contextmanager
    def _lock(self):
        path = _plain(self._root / 'state/workflow.lock')
        held = self._trusted.existing_run_lock
        if held is not None:
            if (type(held) is not RunLock or held.path != path or held.stream is None
                    or held.stream.closed):
                _fail('actual_workflow_lock_ownership_required')
            yield
        else:
            with RunLock(path):
                yield

    def _context(self, request, at):
        value = self._read(self._trusted.read_context, GameContext)
        _integer(value.observed_at_ms, 0, 9_223_372_036_854_775_807)
        if (value.machine_nonce != self._trusted.machine_nonce or value.run_id != request.run_id
                or not 0 <= at - value.observed_at_ms <= 1500):
            _fail('actual_runner_binding_not_current')
        for text in (value.account_identity, value.capture_session, value.backend_generation):
            _text(text, 256)
        _integer(value.process_id, 1)
        if (type(value.process_started_utc_ticks) is not str
                or not re.fullmatch('[0-9]{1,20}', value.process_started_utc_ticks)):
            _fail('exact_native_process_ticks_string_required')
        for digest in (value.executable_sha256, value.native_assembly_sha256, value.actual_binding_sha256):
            _sha(digest)
        return value

    @staticmethod
    def _same_binding(first, second):
        # A fresh actual binding read changes its timestamp, never its process/session identity.
        left, right = asdict(first), asdict(second)
        left.pop('observed_at_ms'); right.pop('observed_at_ms')
        return left == right

    def _sources(self, sources, context, at, *, minimum_at=0, fresh=False):
        if type(sources) is not tuple or not sources:
            _fail('complete_original_sources_required')
        seen = set()
        for source in sources:
            if type(source) is not RawSource or source.relative_path in seen:
                _fail('unique_typed_original_sources_required')
            seen.add(source.relative_path)
            _integer(source.observed_at_ms, 0, 9_223_372_036_854_775_807)
            relative = Path(source.relative_path)
            if (relative.is_absolute() or '..' in relative.parts or ':' in source.relative_path
                    or '\\' in source.relative_path or not relative.parts
                    or relative.parts[0] not in ('logs', 'state')):
                _fail('original_source_must_stay_in_private_root')
            path = _plain(self._root / relative)
            if (source.binding_sha256 != context.actual_binding_sha256
                    or source.capture_session != context.capture_session
                    or not minimum_at <= source.observed_at_ms <= at
                    or (fresh and at - source.observed_at_ms > 1500)):
                _fail('original_source_binding_or_time_invalid')
            _integer(source.length, 1, 32_000_000)
            _sha(source.sha256)
            if not path.is_file() or path.stat().st_size != source.length or _hash(path.read_bytes()) != source.sha256:
                _fail('retained_original_source_changed_or_missing')

    @staticmethod
    def _names(rows, *, costs=False):
        if type(rows) is not tuple or not rows:
            _fail('immutable_named_resources_required')
        result = {}
        for row in rows:
            if costs:
                if type(row) is not MaterialCost:
                    _fail('typed_cost_required')
                name, amount = row.name, row.required
                _integer(row.owned)
                # Native24 explicit zero route is still unaccepted.
                if row.owned <= amount:
                    _fail('zero_inventory_after_route_unaccepted')
            else:
                if type(row) is not tuple or len(row) != 2:
                    _fail('immutable_named_pair_required')
                name, amount = row
            _text(name, 80)
            if name in result or any(word in name.lower() for word in ('树脂', '樹脂', '原石', 'resin', 'primogem')):
                _fail('duplicate_or_forbidden_resource')
            result[name] = _integer(amount, 1 if costs else 0)
        return result

    def _grant(self, request, context, at):
        grant = self._read(self._trusted.read_grant, LocalGrant, request.authorization_id)
        if (grant.authorization_id != request.authorization_id
                or grant.machine_nonce != self._trusted.machine_nonce
                or grant.account_identity != context.account_identity
                or grant.character_name != request.character_name
                or type(grant.approved_at_ms) is not int or type(grant.expires_at_ms) is not int
                or not grant.approved_at_ms <= at < grant.expires_at_ms
                or grant.game_day != _day(at)):
            _fail('existing_human_grant_expired_or_scope_mismatch')
        _sha(grant.source_sha256)
        if (type(grant.talent_targets) is not tuple or len(grant.talent_targets) != 3
                or set(dict(grant.talent_targets)) != {'normal', 'skill', 'burst'}):
            _fail('immutable_three_talent_grant_required')
        for name, ceiling in grant.talent_targets:
            _integer(ceiling, 1, 9)
        if dict(grant.talent_targets)[request.talent_type] < request.target_base_level:
            _fail('target_exceeds_existing_grant')
        self._names(grant.material_caps)
        _integer(grant.mora_cap)
        return grant

    def _holds(self, context, at):
        holds = self._read(self._trusted.read_account_holds, AccountResourceHolds, context)
        if (holds.machine_nonce != context.machine_nonce or holds.account_identity != context.account_identity
                or not 0 <= at - holds.observed_at_ms <= 1500
                or type(holds.unresolved_transaction_ids) is not tuple):
            _fail('complete_account_wide_resource_hold_receipt_required')
        # Ledger enumerator is trusted, but retained complete enumeration bytes must be pinned.
        self._sources(holds.ledger_sources, context, at)
        if holds.unresolved_transaction_ids:
            _fail('existing_account_resource_unknown_blocks_all_consumption')

    def _account(self, context):
        directory = _plain(self._root / 'state/talent-transaction-ledger')
        directory.mkdir(parents=True, exist_ok=True)
        identity = {'schemaVersion': 1, 'machineNonceSha256': _hash(context.machine_nonce.encode())}
        identity_path = directory / 'host-identity.json'
        if identity_path.exists():
            if self._json(identity_path) != identity:
                _fail('local_machine_nonce_replacement_rejected')
        else:
            if any(directory.iterdir()):
                _fail('missing_host_identity_with_existing_records')
            self._write_once(identity_path, identity)
        account = directory / _hash((context.machine_nonce + '\0' + context.account_identity).encode())
        _plain(account).mkdir(exist_ok=True)
        return account

    def _json(self, path):
        _plain(path)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    _fail('duplicate_journal_key')
                result[key] = value
            return result
        try:
            if path.stat().st_size > 8_000_000:
                _fail('journal_unbounded')
            envelope = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                parse_constant=lambda value: _fail('nonfinite_journal_number'))
            if type(envelope) is not dict or set(envelope) != {'payload', 'hmacSha256'}:
                _fail('authenticated_durable_envelope_required')
            expected = hmac.new(self._trusted.ledger_key, _bytes(envelope['payload']), hashlib.sha256).hexdigest()
            if type(envelope['hmacSha256']) is not str or not hmac.compare_digest(expected, envelope['hmacSha256']):
                _fail('durable_record_authentication_failed')
            return envelope['payload']
        except (OSError, ValueError, TypeError):
            _fail('corrupt_or_partial_journal_blocks_account')

    def _write_once(self, path, value):
        _plain(path)
        data = _bytes({'payload': value, 'hmacSha256': hmac.new(self._trusted.ledger_key,
            _bytes(value), hashlib.sha256).hexdigest()})
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != data:
            _fail('durable_exact_readback_failed')
        # POSIX directory entries also need durability; Windows fsync flushes file handle.
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return _hash(data)

    def _usage(self, account, grant):
        used, mora = {}, 0
        fingerprint = _hash(_bytes(asdict(grant)))
        for directory in account.iterdir():
            if not directory.is_dir():
                _fail('unexpected_account_ledger_entry')
            _plain(directory)
            row = self._json(directory / 'reservation.json')
            terminal = self._json(directory / 'terminal.json')
            if (row.get('schemaVersion') != 1 or terminal.get('schemaVersion') != 1
                    or terminal.get('reservationSha256') != _hash((directory / 'reservation.json').read_bytes())
                    or terminal.get('kind') not in ('success', 'no_submission')
                    or terminal.get('accountScope') != account.name
                    or terminal.get('nativeConsumptionEnabled') is not False
                    or set(p.name for p in directory.iterdir()) != {'reservation.json', 'outcome.json', 'terminal.json'}):
                _fail('unresolved_account_transaction_blocks_all_consumption')
            outcome = self._json(directory / 'outcome.json')
            if terminal.get('outcomeSha256') != _hash((directory / 'outcome.json').read_bytes()) or outcome.get('kind') != terminal['kind']:
                _fail('terminal_outcome_mismatch')
            try:
                original_context = GameContext(**row['context'])
                original_request = TalentStepRequest(**row['request'])
                self._request(original_request)
                expected_scope = _hash((original_context.machine_nonce + '\0' + original_context.account_identity).encode())
                expected_step = _hash((original_request.run_id + '\0' + original_request.step_id).encode())
                if (row['accountScope'] != account.name or expected_scope != account.name
                        or directory.name != expected_step or outcome['request'] != row['request']
                        or not self._same_binding(GameContext(**outcome['context']), original_context)):
                    _fail('prior_account_journal_identity_mismatch')
                source_groups = [row['before']['sources'], outcome['submission_sources'], outcome['world']['sources']]
                if outcome['after'] is not None:
                    source_groups.append(outcome['after']['sources'])
                for sources in source_groups:
                    self._sources(tuple(RawSource(**s) for s in sources), original_context, _now_ms())
            except (KeyError, TypeError):
                _fail('incomplete_prior_original_source_chain')
            if row.get('grant', {}).get('authorization_id') == grant.authorization_id:
                if row.get('grantSha256') != fingerprint or row.get('grant') != json.loads(_bytes(asdict(grant))):
                    _fail('immutable_original_grant_changed')
                if terminal['kind'] == 'success':
                    for name, amount in row['materialReservation']:
                        used[name] = used.get(name, 0) + _integer(amount, 1)
                    mora += _integer(row['moraReservation'], 1)
        return used, mora

    def issue_permit(self, request):
        self._request(request)
        with self._lock():
            at = _now_ms()
            context = self._context(request, at)
            grant = self._grant(request, context, at)
            self._holds(context, at)
            before = self._read(self._trusted.read_before, VerifiedBefore, request, context)
            _integer(before.base_level, 1, 8)
            _integer(before.display_level, 1, 11)
            _integer(before.observed_at_ms, 0, 9_223_372_036_854_775_807)
            _text(before.talent_name)
            if (before.request != request or not self._same_binding(before.context, context) or not before.talent_name
                    or before.base_level != request.expected_base_level
                    or type(before.fixed_plus_three) is not bool
                    or before.display_level != before.base_level + (3 if before.fixed_plus_three else 0)
                    or not 0 <= at - before.observed_at_ms <= 1500 or not 1 <= len(before.materials) <= 4):
                _fail('complete_verified_before_scope_mismatch')
            costs = self._names(before.materials, costs=True)
            # Preparation identity/tooltips precede the final popup and may be older.
            # The strict native verifier owns that complete timeline; only final popup
            # sources and the authenticated before acceptance must be input-fresh here.
            self._sources(before.sources, context, at, minimum_at=grant.game_day * 86_400_000 - 4 * 3_600_000)
            required_kinds = {'character', 'talent_entry', 'talent_detail', 'popup', 'mora'}
            if not required_kinds <= {s.kind for s in before.sources}:
                _fail('complete_raw_before_categories_required')
            popup_sources = tuple(sorted((s for s in before.sources if s.kind == 'popup'), key=lambda s: s.observed_at_ms))
            if len(popup_sources) < 2:
                _fail('final_popup_pair_sources_required')
            if popup_sources[-2].observed_at_ms >= popup_sources[-1].observed_at_ms:
                _fail('independent_ordered_final_popup_pair_required')
            self._sources(popup_sources[-2:], context, at, fresh=True)
            for name in costs:
                if sum(s.kind == 'material_tooltip' and s.name == name for s in before.sources) < 2:
                    _fail('full_named_material_pair_sources_required')
            _integer(before.mora_required, 1)
            if _integer(before.mora_owned) <= before.mora_required:
                _fail('zero_mora_after_route_unaccepted')
            account = self._account(context)
            step = account / _hash((request.run_id + '\0' + request.step_id).encode())
            if step.exists():
                _fail('duplicate_run_step_never_replayed')
            used, mora = self._usage(account, grant)
            caps = self._names(grant.material_caps)
            if any(used.get(name, 0) + amount > caps.get(name, 0) for name, amount in costs.items()) or mora + before.mora_required > grant.mora_cap:
                _fail('original_named_budget_exhausted')
            # Recheck real wall clock and actual runner context after original evidence I/O.
            final_at = _now_ms()
            if not self._same_binding(self._context(request, final_at), context) or final_at >= grant.expires_at_ms or _day(final_at) != grant.game_day:
                _fail('binding_or_grant_changed_before_reservation')
            if final_at - before.observed_at_ms > 1500:
                _fail('before_stale_after_evidence_io')
            # A newer summary timestamp cannot refresh either original popup frame.
            # Check their actual capture times again after source/old-ledger I/O.
            if any(not 0 <= final_at - source.observed_at_ms <= 1500 for source in popup_sources[-2:]):
                _fail('final_popup_pair_stale_after_evidence_io')
            row = {'schemaVersion': 1, 'accountScope': account.name, 'grant': asdict(grant),
                'grantSha256': _hash(_bytes(asdict(grant))), 'request': asdict(request),
                'context': asdict(context), 'before': asdict(before),
                'materialReservation': tuple(costs.items()), 'moraReservation': before.mora_required,
                'reservedAtMs': final_at, 'nativeConsumptionEnabled': False}
            step.mkdir()
            digest = self._write_once(step / 'reservation.json', row)
            permit = TalentSpendPermit(account.name, grant.authorization_id, request, context.capture_session,
                context.actual_binding_sha256, grant.expires_at_ms, grant.game_day,
                tuple(costs.items()), before.mora_required, digest)
            self._permits[id(permit)] = (permit, step, row, before)
            return permit

    def _permit(self, permit):
        retained = self._permits.get(id(permit))
        if retained is None or retained[0] is not permit or type(permit) is not TalentSpendPermit:
            _fail('same_process_exact_permit_required_no_cross_run_replay')
        _, step, row, before = retained
        if _hash((step / 'reservation.json').read_bytes()) != permit.reservation_sha256 or self._json(step / 'reservation.json') != json.loads(_bytes(row)):
            _fail('reservation_changed')
        if (step / 'terminal.json').exists() or (step / 'outcome.json').exists():
            _fail('permit_already_finalized_or_partial_finalization')
        return step, row, before

    def assert_still_valid(self, permit):
        with self._lock():
            _, row, before = self._permit(permit)
            at = _now_ms()
            current = self._context(permit.request, at)
            if not self._same_binding(current, before.context):
                _fail('actual_game_binding_changed')
            if json.loads(_bytes(asdict(self._grant(permit.request, current, at)))) != json.loads(_bytes(row['grant'])):
                _fail('immutable_original_grant_changed')
            if at >= permit.expires_at_ms or _day(at) != permit.game_day:
                _fail('original_grant_expired')
            self._sources(before.sources, before.context, at)
            return permit

    def native_admission(self, *_args, **_kwargs):
        # No Host JSON token can satisfy Native24 CurrentPopup or enable a consumer.
        raise NotImplementedError('Unintegrated: same-process native final popup gate is disabled')

    def finalize(self, permit):
        """Reads authenticated outcome from trusted adapter; caller supplies no result bool."""
        with self._lock():
            step, row, before = self._permit(permit)
            at = _now_ms()
            outcome = self._read(self._trusted.read_outcome, VerifiedOutcome, permit.request, before.context)
            if (outcome.request != permit.request or not self._same_binding(outcome.context, before.context)
                    or not self._same_binding(self._context(permit.request, at), before.context)):
                _fail('independent_outcome_scope_mismatch')
            # Expiry blocks further input, not delayed independent accounting/recovery.
            self._sources(outcome.submission_sources, before.context, at, minimum_at=row['reservedAtMs'])
            world = outcome.world
            if world is None:
                _fail('world_restoration_unknown_reservation_retained')
            _integer(world.first_at_ms, 0, 9_223_372_036_854_775_807)
            _integer(world.second_at_ms, 0, 9_223_372_036_854_775_807)
            if (type(world) is not VerifiedWorld or not row['reservedAtMs'] <= world.first_at_ms < world.second_at_ms <= at
                    or world.second_at_ms - world.first_at_ms > 5000 or at - world.second_at_ms > 1500
                    or len(world.sources) != 2 or any(s.kind != 'world_restore' for s in world.sources)):
                _fail('independent_world_pair_required')
            self._sources(world.sources, before.context, at, minimum_at=world.first_at_ms, fresh=True)
            if sorted(s.observed_at_ms for s in world.sources) != [world.first_at_ms, world.second_at_ms]:
                _fail('world_pair_source_times_mismatch')
            if outcome.kind == 'success':
                if (type(outcome.submission_at_ms) is not int or not row['reservedAtMs'] <= outcome.submission_at_ms < permit.expires_at_ms
                        or _day(outcome.submission_at_ms) != permit.game_day
                        or len(outcome.submission_sources) != 1 or outcome.submission_sources[0].kind != 'commit_armed'
                        or outcome.submission_sources[0].observed_at_ms != outcome.submission_at_ms):
                    _fail('independent_native_once_commit_gate_required')
                after = outcome.after
                if type(after) is VerifiedAfter:
                    _integer(after.base_level, 2, 9)
                    _integer(after.display_level, 2, 12)
                    _integer(after.observed_at_ms, 0, 9_223_372_036_854_775_807)
                if (type(after) is not VerifiedAfter or after.talent_name != before.talent_name
                        or type(after.fixed_plus_three) is not bool or after.fixed_plus_three != before.fixed_plus_three
                        or after.base_level != before.base_level + 1
                        or after.display_level != after.base_level + (3 if after.fixed_plus_three else 0)
                        or not outcome.submission_at_ms < after.observed_at_ms <= world.second_at_ms):
                    _fail('independent_exact_base_plus_one_required')
                counts = self._names(after.material_counts)
                if set(counts) != {c.name for c in before.materials} or any(c.owned - counts[c.name] != c.required for c in before.materials):
                    _fail('independent_all_old_material_deltas_required')
                if before.mora_owned - _integer(after.mora) != before.mora_required:
                    _fail('independent_exact_mora_delta_required')
                self._sources(after.sources, before.context, at, minimum_at=outcome.submission_at_ms + 1)
                if not {'character', 'talent_detail', 'mora'} <= {s.kind for s in after.sources}:
                    _fail('complete_after_sources_required')
                for name in counts:
                    if sum(s.kind == 'named_inventory' and s.name == name for s in after.sources) < 2:
                        _fail('every_old_named_inventory_pair_required')
                if world.first_at_ms < after.observed_at_ms:
                    _fail('world_restore_must_follow_independent_after')
            elif outcome.kind == 'no_submission':
                if (outcome.after is not None or outcome.submission_at_ms is not None
                        or len(outcome.submission_sources) != 1 or outcome.submission_sources[0].kind != 'positive_no_submission'):
                    _fail('positive_native_no_submission_proof_required')
                if world.first_at_ms < outcome.submission_sources[0].observed_at_ms:
                    _fail('world_restore_must_follow_no_submission')
            else:
                _fail('unknown_reservation_retained_all_account_consumption_blocked')
            digest = self._write_once(step / 'outcome.json', asdict(outcome))
            terminal = {'schemaVersion': 1, 'kind': outcome.kind, 'accountScope': permit.account_scope,
                'reservationSha256': permit.reservation_sha256, 'outcomeSha256': digest,
                'nativeConsumptionEnabled': False, 'finalizedAtMs': at}
            self._write_once(step / 'terminal.json', terminal)
            return outcome.kind
