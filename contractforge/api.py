import json
import os
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from .models import ReplayRequest
from .engine import replay
from .store import Store, Conflict
from .security import Boundary

HERE = Path(__file__).parent


def create_app(db_path=None):
    app = FastAPI(title='ContractForge', version='0.1.0', docs_url=None, redoc_url=None)
    store = Store(db_path or os.getenv('DB_PATH', 'data/contractforge.db'))
    app.add_middleware(Boundary)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'contractforge'}

    @app.get('/api/scenarios')
    def scenarios():
        return [{'id': p.stem, 'title': json.loads(p.read_text())['title']} for p in sorted((HERE / 'fixtures').glob('*.json'))]

    @app.get('/api/scenarios/{scenario_id}')
    def scenario(scenario_id: str):
        path = next((p for p in (HERE / 'fixtures').glob('*.json') if p.stem == scenario_id), None)
        if not path:
            raise HTTPException(404, 'Scenario not found')
        return json.loads(path.read_text())

    @app.post('/api/replays')
    def create(request: ReplayRequest, idempotency_key: str | None = Header(default=None, max_length=128)):
        body = request.model_dump(mode='json')
        key = idempotency_key or str(uuid4())
        try:
            cached = store.cached(key, body)
            return cached or store.save(key, body, replay(request))
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:200]) from exc

    @app.get('/api/replays')
    def recent():
        return store.recent()

    @app.get('/api/replays/{report_id}')
    def report(report_id: str):
        result = store.get(report_id)
        if result is None:
            raise HTTPException(404, 'Replay not found')
        return result

    app.mount('/', StaticFiles(directory=HERE / 'web', html=True), name='web')
    return app


app = create_app()
