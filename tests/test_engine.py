import copy
import json
from pathlib import Path
import pytest
from contractforge.models import ReplayRequest
from contractforge.engine import replay, convert
from contractforge import llm

def fixture(name='01-safe-migration'):
    return json.loads((Path(__file__).parents[1]/'examples'/f'{name}.json').read_text())

@pytest.mark.parametrize('scenario,accepted,quarantined,gate',[('01-safe-migration',8,0,'pass'),('02-lossy-cast',3,5,'block'),('03-enum-break',6,2,'block')])
def test_scenarios(scenario,accepted,quarantined,gate):
    r=replay(ReplayRequest(**fixture(scenario)))
    assert r['summary']['accepted']==accepted
    assert r['summary']['quarantined']==quarantined
    assert r['summary']['gate']==gate

def test_money_and_identity_preserved_without_mutation():
    body=fixture();before=copy.deepcopy(body)
    r=replay(ReplayRequest(**body))
    assert r['records'][0]['candidate']['amount']==12.99
    assert r['records'][0]['candidate']['buyer_id']=='buyer-001'
    assert body==before

def test_unit_change_still_checks_integer_cast_when_declared_types_match():
    r=replay(ReplayRequest(**fixture('02-lossy-cast')))
    assert {'op':'cast','field':'amount','to':'integer'} in r['plan']['operations']
    assert r['records'][0]['errors']==['Lossy integer conversion rejected']

@pytest.mark.parametrize('value,target',[('12.99','integer'),('maybe','boolean'),({},'string'),('2026-10-11T00:00:00','timestamp'),(True,'integer'),('NaN','number'),('Infinity','number')])
def test_unsafe_casts_rejected(value,target):
    with pytest.raises(ValueError):convert(value,target)

def test_duplicate_ids_quarantined():
    body=fixture();body['events'].append(copy.deepcopy(body['events'][0]))
    r=replay(ReplayRequest(**body))
    assert r['summary']['quarantined']==1
    assert r['records'][-1]['errors']==['Duplicate event identity in replay']

def test_rename_will_not_overwrite_extra_field():
    body=fixture();body['events'][0]['buyer_id']='different-buyer'
    r=replay(ReplayRequest(**body))
    assert r['records'][0]['status']=='quarantined'
    assert r['records'][0]['original']['buyer_id']=='different-buyer'

def test_invalid_source_stays_in_quarantine():
    body=fixture();del body['events'][0]['customer_id']
    r=replay(ReplayRequest(**body))
    assert not r['records'][0]['source_valid']
    assert r['records'][0]['candidate'] is None

def test_business_invariant_catches_missing_scale():
    body=fixture();body['plan']={'rationale':'Bad plan misses the cents conversion.','operations':[
        {'op':'rename','source':'customer_id','target':'buyer_id'},
        {'op':'rename','source':'amount_cents','target':'amount'},
        {'op':'rename','source':'event_time','target':'occurred_at'}]}
    r=replay(ReplayRequest(**body))
    assert 'order_value: business value changed' in r['records'][0]['errors']
    assert r['summary']['gate']=='block'

def test_arbitrary_code_is_not_in_the_dsl():
    body=fixture();body['plan']={'rationale':'not allowed','operations':[{'op':'exec','code':'print(1)'}]}
    with pytest.raises(ValueError):ReplayRequest(**body)

def test_undeclared_rename_rejected():
    body=fixture();body['plan']={'rationale':'guess','operations':[{'op':'rename','source':'country','target':'buyer_id'}]}
    with pytest.raises(ValueError):replay(ReplayRequest(**body))

def test_ai_plan_uses_same_replay_validator(monkeypatch):
    body=fixture('02-lossy-cast');body['analyst']='ollama'
    good=replay(ReplayRequest(**fixture('02-lossy-cast')))['plan']
    monkeypatch.setattr(llm,'generate',lambda *args:good)
    r=replay(ReplayRequest(**body))
    assert r['analyst']=='ollama'
    assert r['summary']['quarantined']==5

def test_ai_hallucination_falls_back(monkeypatch):
    body=fixture();body['analyst']='ollama'
    monkeypatch.setattr(llm,'generate',lambda *args:{'rationale':'unsafe','operations':[{'op':'scale','field':'amount','factor':'100'}]})
    r=replay(ReplayRequest(**body))
    assert r['ai_status']=='rejected_or_unavailable'
    assert r['summary']['gate']=='pass'

def test_gate_threshold_is_explicit():
    body=fixture('03-enum-break');body['max_reject_rate']=.25
    r=replay(ReplayRequest(**body))
    assert r['summary']['gate']=='pass'
    assert r['summary']['quarantined']==2

def test_nonfinite_in_extra_fields_rejected():
    body=fixture();body['events'][0]['extra']={'nested':float('nan')}
    with pytest.raises(ValueError):replay(ReplayRequest(**body))

def test_nullable_value_preserved():
    body=fixture();body['source']['fields'][1]['nullable']=True;body['target']['fields'][1]['nullable']=True
    body['events'][0]['customer_id']=None
    r=replay(ReplayRequest(**body))
    assert r['records'][0]['status']=='accepted'
    assert r['records'][0]['candidate']['buyer_id'] is None
