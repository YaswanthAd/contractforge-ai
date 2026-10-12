"""Pure contract diff, restricted migration DSL, and loss-aware event replay."""
import copy
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .models import Contract, Plan, ReplayRequest, Rename, Cast, Scale
from . import llm


def matches(target, source):
    fields = {f.name: f for f in source.fields}
    if target.name in fields:
        return fields[target.name]
    candidates = [fields[a] for a in target.aliases if a in fields]
    return candidates[0] if len(candidates) == 1 else None


def diff(source: Contract, target: Contract):
    changes = []
    matched = set()
    for field in target.fields:
        old = matches(field, source)
        if not old:
            changes.append({'field': field.name, 'kind': 'required_added' if field.required else 'optional_added',
                            'breaking': field.required, 'detail': 'No unambiguous source field or alias'})
            continue
        matched.add(old.name)
        if old.name != field.name:
            changes.append({'field': field.name, 'kind': 'rename', 'breaking': True, 'detail': f'{old.name} → {field.name}'})
        if old.type != field.type:
            changes.append({'field': field.name, 'kind': 'type_change', 'breaking': True, 'detail': f'{old.type} → {field.type}'})
        if old.unit != field.unit:
            changes.append({'field': field.name, 'kind': 'unit_change', 'breaking': True, 'detail': f'{old.unit} → {field.unit}'})
        if (field.required and not old.required) or (old.nullable and not field.nullable):
            changes.append({'field': field.name, 'kind': 'presence_tightened', 'breaking': True, 'detail': 'Presence or nullability narrowed'})
        if field.enum and (not old.enum or not set(old.enum) <= set(field.enum)):
            changes.append({'field': field.name, 'kind': 'enum_narrowed', 'breaking': True, 'detail': 'Some previously allowed values are rejected'})
    for old in source.fields:
        if old.name not in matched:
            changes.append({'field': old.name, 'kind': 'removed', 'breaking': True, 'detail': 'No target mapping; original data retained in replay'})
    if source.allow_extra and not target.allow_extra:
        changes.append({'field': '*', 'kind': 'extras_disallowed', 'breaking': True, 'detail': 'Previously allowed extra fields now rejected'})
    return changes


def propose(source, target):
    operations = []
    for field in target.fields:
        old = matches(field, source)
        if not old:
            continue
        if old.name != field.name:
            operations.append(Rename(op='rename', source=old.name, target=field.name))
        if old.unit != field.unit and old.unit and field.unit:
            operations.append(Scale(op='scale', field=field.name, factor='0.01' if old.unit == 'cents' else '100'))
        if old.type != field.type or (old.unit != field.unit and old.unit and field.unit):
            operations.append(Cast(op='cast', field=field.name, to=field.type))
    return Plan(rationale='Use explicit aliases and units. Preserve values; quarantine ambiguous or lossy conversions.', operations=operations)


def validate_plan(plan, source, target):
    available = {f.name for f in source.fields}
    fields = {f.name: f for f in target.fields}
    for op in plan.operations:
        if isinstance(op, Rename):
            if op.source not in available or op.target not in fields or op.target in available:
                raise ValueError('Rename must use an existing source and an unoccupied target field')
            original = matches(fields[op.target], source)
            if original is None or original.name != op.source:
                raise ValueError('Rename must follow an explicit unambiguous alias')
            available.remove(op.source)
            available.add(op.target)
        elif isinstance(op, Cast):
            if op.field not in available or op.field not in fields or op.to != fields[op.field].type:
                raise ValueError('Cast must match the declared target field type')
        elif isinstance(op, Scale):
            if op.field not in available or op.field not in fields:
                raise ValueError('Scale field must exist in source and target')
            old = matches(fields[op.field], source)
            expected = {('cents', 'usd'): '0.01', ('usd', 'cents'): '100'}.get((old.unit if old else None, fields[op.field].unit))
            if op.factor != expected:
                raise ValueError('Scale must match explicit source and target units')


def decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('Expected a finite number')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid numeric value') from exc
    if not number.is_finite() or abs(number) > Decimal('1e15'):
        raise ValueError('Numeric value outside supported finite range')
    return number


def convert(value, target):
    if value is None:
        return None
    if target == 'integer':
        d = decimal(value)
        if d != d.to_integral_value():
            raise ValueError('Lossy integer conversion rejected')
        return int(d)
    if target == 'number':
        d = decimal(value)
        output = float(d)
        if Decimal(str(output)) != d:
            raise ValueError('Lossy floating-point conversion rejected')
        return output
    if target == 'string':
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError('Object-to-string conversion rejected')
        return str(value)
    if target == 'boolean':
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {'true', 'false'}:
            return value.lower() == 'true'
        raise ValueError('Ambiguous boolean conversion rejected')
    if target == 'timestamp':
        if not isinstance(value, str):
            raise ValueError('Timestamp must be an ISO 8601 string')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('Timestamp requires a timezone')
        return parsed.isoformat()
    raise ValueError('Unsupported conversion')


def validate_event(event, contract):
    errors = []
    for field in contract.fields:
        if field.name not in event:
            if field.required:
                errors.append(f'{field.name}: required field missing')
            continue
        value = event[field.name]
        if value is None:
            if not field.nullable:
                errors.append(f'{field.name}: null is not allowed')
            continue
        valid = {
            'string': isinstance(value, str),
            'integer': isinstance(value, int) and not isinstance(value, bool),
            'number': isinstance(value, (int, float)) and not isinstance(value, bool),
            'boolean': isinstance(value, bool),
            'timestamp': isinstance(value, str),
        }[field.type]
        if not valid:
            errors.append(f'{field.name}: expected {field.type}')
            continue
        try:
            if field.type == 'timestamp':
                convert(value, 'timestamp')
            if field.type in {'integer', 'number'}:
                decimal(value)
        except ValueError as exc:
            errors.append(f'{field.name}: {exc}')
        if field.enum and value not in field.enum:
            errors.append(f'{field.name}: value is outside the target enum')
    if not contract.allow_extra:
        extras = set(event) - {f.name for f in contract.fields}
        errors += [f'{name}: extra field not allowed' for name in sorted(extras)]
    return errors


def transform(event, plan):
    output = copy.deepcopy(event)
    for op in plan.operations:
        if isinstance(op, Rename):
            if op.source not in output:
                continue
            if op.target in output:
                raise ValueError(f'{op.target}: rename would overwrite existing data')
            output[op.target] = output.pop(op.source)
        elif op.field in output and output[op.field] is not None:
            if isinstance(op, Cast):
                output[op.field] = convert(output[op.field], op.to)
            elif isinstance(op, Scale):
                value = decimal(output[op.field]) * Decimal(op.factor)
                output[op.field] = int(value) if value == value.to_integral_value() else convert(str(value), 'number')
    return output


def invariants(before, after, source, target):
    errors = []
    semantic_targets = {f.semantic: f for f in target.fields if f.semantic}
    for old in source.fields:
        if not old.semantic or old.name not in before:
            continue
        new = semantic_targets.get(old.semantic)
        if not new or new.name not in after:
            errors.append(f'{old.semantic}: semantic value has no target mapping')
            continue
        left, right = before[old.name], after[new.name]
        if left is None and right is None:
            continue
        try:
            if old.unit and new.unit:
                left = decimal(left) * (Decimal('.01') if old.unit == 'cents' else 1)
                right = decimal(right) * (Decimal('.01') if new.unit == 'cents' else 1)
            if left != right:
                errors.append(f'{old.semantic}: business value changed')
        except ValueError:
            errors.append(f'{old.semantic}: cannot compare business values')
    return errors


def replay(request: ReplayRequest):
    # JSON serialization also rejects non-finite numbers nested in arbitrary events.
    json.dumps(request.events, allow_nan=False)
    plan = request.plan or propose(request.source, request.target)
    analyst, ai_status, ai_error = 'evidence_engine', 'not_requested', None
    if request.plan:
        analyst = 'user_plan'
    elif request.analyst == 'ollama':
        try:
            raw = llm.generate('Propose a conservative event migration using only rename, cast and scale operations. '
                               'Use declared aliases and units. Never invent defaults or drop fields. '
                               'Some events should be quarantined rather than changed.',
                               {'source': request.source.model_dump(), 'target': request.target.model_dump(),
                                'sample': request.events[:20]}, Plan.model_json_schema())
            candidate = Plan.model_validate(raw)
            validate_plan(candidate, request.source, request.target)
            plan, analyst, ai_status = candidate, 'ollama', 'validated'
        except (llm.ProviderError, ValueError) as exc:
            ai_status, ai_error = 'rejected_or_unavailable', str(exc)[:180]
    validate_plan(plan, request.source, request.target)
    records, seen = [], set()
    for index, event in enumerate(request.events):
        errors = validate_event(event, request.source)
        before_errors = list(errors)
        output = None
        if not errors:
            try:
                output = transform(event, plan)
                errors = validate_event(output, request.target)
                errors += invariants(event, output, request.source, request.target)
                if request.target.identity_field and not errors:
                    value = output.get(request.target.identity_field)
                    if value is None or not isinstance(value, (str, int)) or isinstance(value, bool):
                        errors.append('Identity must be a non-null string or integer')
                    else:
                        identity = (type(value).__name__, value)
                        if identity in seen:
                            errors.append('Duplicate event identity in replay')
                        else:
                            seen.add(identity)
            except ValueError as exc:
                errors.append(str(exc))
        records.append({'index': index, 'original': event, 'candidate': output,
                        'status': 'quarantined' if errors else 'accepted',
                        'source_valid': not before_errors, 'errors': errors})
    accepted = sum(r['status'] == 'accepted' for r in records)
    rejected = len(records) - accepted
    rate = rejected / len(records)
    changes = diff(request.source, request.target)
    return {'title': request.title, 'analyst': analyst, 'ai_status': ai_status, 'ai_error': ai_error,
            'source': request.source.model_dump(), 'target': request.target.model_dump(),
            'plan': plan.model_dump(), 'changes': changes, 'records': records,
            'summary': {'total': len(records), 'accepted': accepted, 'quarantined': rejected,
                        'reject_rate': rate, 'max_reject_rate': request.max_reject_rate,
                        'gate': 'pass' if rate <= request.max_reject_rate else 'block',
                        'scope': 'Observed replay only; this does not prove compatibility for unseen events.'},
            'counterexamples': [r for r in records if r['errors']][:10]}
