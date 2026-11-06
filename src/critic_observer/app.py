"""One ASGI application serves the UI, collection API, and MCP transport."""

import fcntl
import hmac
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import __version__
from .auth import COOKIE, AccessMiddleware, session_token
from .config import Settings
from .mcp_server import build_mcp, observations
from .metrics import assessment_queue, calculate, compare_experiment
from .models import Batch, Critic, Experiment, ReviewType
from .specialties import specialty_of
from .store import Conflict, Store

log = logging.getLogger(__name__)
WEB = Path(__file__).parent / "web"


class Login(BaseModel):
    token: str = Field(max_length=1000)


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    store = Store(settings.database)
    mcp = build_mcp(store, settings)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        lock_path = settings.database.with_suffix(".lock")
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "Another observer process owns this database; use one replica"
                ) from exc
            for critic in json.loads((Path(__file__).parent / "builtin_critics.json").read_text()):
                store.register_critic(Critic.model_validate(critic))
            async with mcp.session_manager.run():
                log.info("observer_started version=%s database=%s", __version__, settings.database)
                yield

    app = FastAPI(
        title="Critic observer",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(AccessMiddleware, settings=settings)

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        log.warning("request_conflict path=%s reason=%s", request.url.path, exc)
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PermissionError)
    async def permission_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.get("/healthz")
    def health():
        with store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": __version__}

    @app.post("/api/login")
    def login(body: Login):
        if not hmac.compare_digest(body.token.encode(), settings.admin_token.encode()):
            raise HTTPException(401, "Invalid operator credential")
        response = JSONResponse({"role": "operator"})
        response.set_cookie(
            COOKIE,
            session_token(settings.admin_token),
            httponly=True,
            secure=settings.public_url.startswith("https://"),
            samesite="strict",
            max_age=43200,
        )
        return response

    @app.get("/api/session")
    def session(request: Request):
        return {"role": request.state.role, "version": __version__}

    @app.post("/api/logout")
    def logout():
        response = Response(status_code=204)
        response.delete_cookie(COOKIE)
        return response

    @app.get("/api/schema")
    def schema():
        return Batch.model_json_schema()

    @app.get("/api/critics")
    def critics():
        return [{**c, "effective_specialty": specialty_of(c)} for c in store.critics()]

    @app.post("/api/critics")
    def register_critic(body: Critic):
        return store.register_critic(body)

    @app.post("/api/events")
    def ingest(body: Batch, request: Request):
        return store.ingest(body, request.state.role)

    @app.get("/api/dashboard")
    def dashboard(
        response: Response,
        project: str = "",
        review_type: ReviewType | Literal[""] = "pull_request",
        client: str = "",
        dataset: str = "production",
        skill_revision: str = "",
        complexity: str = "",
        experiment_id: str = "",
        variant_id: str = "",
        case_id: str = "",
        since: str = "",
        until: str = "",
    ):
        filters = dict(
            project=project,
            review_type=review_type,
            client=client,
            dataset=dataset,
            skill_revision=skill_revision,
            complexity=complexity,
            experiment_id=experiment_id,
            variant_id=variant_id,
            case_id=case_id,
            since=since,
            until=until,
        )
        started = perf_counter()
        snapshot = store.snapshot(filters)
        read_finished = perf_counter()
        metrics = calculate(snapshot, store.critics())
        assessment = assessment_queue(snapshot)
        finished = perf_counter()
        response.headers["Server-Timing"] = (
            f"snapshot;dur={(read_finished - started) * 1000:.2f}, "
            f"metrics;dur={(finished - read_finished) * 1000:.2f}"
        )
        if finished - started >= 1:
            log.warning(
                "dashboard_slow snapshot_seconds=%.3f metrics_seconds=%.3f runs=%d",
                read_finished - started,
                finished - read_finished,
                len(snapshot["runs"]),
            )
        return {
            "metrics": metrics,
            "assessment": assessment,
            "runs": snapshot["runs"],
            "filters": filters,
        }

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        return store.run(run_id)

    @app.get("/api/runs/{run_id}/observations")
    def observed(run_id: str):
        return observations(store.run(run_id))

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str):
        return JSONResponse(
            store.export_bundle(run_id),
            headers={"Content-Disposition": 'attachment; filename="review-export.json"'},
        )

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str):
        store.delete_run(run_id)
        return {"deleted": run_id}

    @app.get("/api/experiments")
    def experiments(review_type: ReviewType | Literal[""] = "pull_request"):
        return store.experiments(review_type)

    @app.post("/api/experiments")
    def create_experiment(body: Experiment):
        return store.create_experiment(body)

    @app.get("/api/experiments/{experiment_id}")
    def experiment(experiment_id: str):
        return compare_experiment(store.experiment(experiment_id), store.snapshot())

    @app.get("/api/experiments/{experiment_id}/brief")
    def brief(experiment_id: str, variant_id: str = Query(), case_id: str = Query()):
        return store.brief(experiment_id, variant_id, case_id)

    @app.get("/api/backup")
    def backup():
        # A history backup may be larger than RAM. Use the database volume,
        # never a container's memory-backed /tmp, and stream the resulting file.
        directory = Path(tempfile.mkdtemp(prefix="observer-backup-", dir=settings.database.parent))
        destination = directory / "observer.sqlite3"
        try:
            store.backup(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            directory.rmdir()
            raise

        def cleanup():
            destination.unlink(missing_ok=True)
            directory.rmdir()

        return FileResponse(
            destination, filename="observer-backup.sqlite3", background=BackgroundTask(cleanup)
        )

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    app.mount("/assets", StaticFiles(directory=WEB), name="assets")
    app.mount("/", mcp_app)
    return app
