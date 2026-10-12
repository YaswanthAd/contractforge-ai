"""Reproduce the three synthetic scenarios. No model or network is required."""
import json
from pathlib import Path
from contractforge.models import ReplayRequest
from contractforge.engine import replay
ROOT=Path(__file__).resolve().parents[1]
expected={'01-safe-migration': (8, 0), '02-lossy-cast': (3, 5), '03-enum-break': (6, 2)}
out=[]
for scenario,expect in expected.items():
    request=ReplayRequest.model_validate_json((ROOT/'examples'/f'{scenario}.json').read_text())
    result=replay(request)
    observed=(result['summary']['accepted'], result['summary']['quarantined'])
    assert observed==expect,(scenario,observed,expect)
    out.append({'scenario':scenario,'expected':expect,'observed':observed,'passed':True})
report={'scope':'Three designed synthetic fixtures; evidence engine only; no LLM quality or load benchmark.','results':out}
(ROOT/'docs/evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
