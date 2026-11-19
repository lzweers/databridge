from contextlib import asynccontextmanager
import csv
import io
import json
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from .connectors import dummyjson
from .database import Base, engine, get_db
from .ingestion import persist_rows, offer_snapshot
from .migrations import upgrade_legacy_schema
from .models import ImportRun, SupplierOffer, ValidationIssue, SourceRow, OfferEvent, PipelineSchedule, PipelineExecution
from .scheduling import update_schedule, trigger_now, serialize_schedule, serialize_execution
from .parsing import MAX_UPLOAD_SIZE, normalize, read_csv, validate_mapping


@asynccontextmanager
async def lifespan(app: FastAPI):
    upgrade_legacy_schema(engine)
    # Local MVP: production deployment should use versioned Alembic migrations.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="DataBridge API", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"], allow_headers=["*"],
)


def require_csv(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Bitte eine CSV-Datei hochladen.")


async def load_file(file: UploadFile) -> tuple[list[str], list[dict[str, str]]]:
    require_csv(file)
    data = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "Maximal 5 MB pro CSV-Datei erlaubt.")
    try:
        return read_csv(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/imports/preview")
async def preview_csv(file: UploadFile = File(...)):
    headers, rows = await load_file(file)
    suggested = {
        "external_id": next((h for h in headers if h.lower() in ("sku", "artikelnummer", "artikelnr", "product_id", "id")), ""),
        "name": next((h for h in headers if h.lower() in ("name", "produktname", "artikelname", "title")), ""),
        "price_eur": next((h for h in headers if h.lower() in ("preis", "price", "price_eur", "unit_price")), ""),
        "stock": next((h for h in headers if h.lower() in ("bestand", "stock", "menge", "quantity")), ""),
    }
    return {"headers": headers, "preview": rows[:5], "total_rows": len(rows), "suggested_mapping": suggested}


@app.post("/api/imports/upload")
async def import_csv(file: UploadFile = File(...), mapping_json: str = Form(...),
                     source_name: str = Form(...), db: Session = Depends(get_db)):
    headers, rows = await load_file(file)
    source_name = source_name.strip()
    if not source_name or len(source_name) > 100:
        raise HTTPException(422, "Quellname muss 1 bis 100 Zeichen enthalten.")
    if source_name == dummyjson.SOURCE_NAME:
        raise HTTPException(422, "Dieser Quellname ist für den API-Connector reserviert.")
    try:
        mapping = json.loads(mapping_json)
        if not isinstance(mapping, dict):
            raise ValueError("Mapping muss ein Objekt sein.")
        validate_mapping(mapping, headers)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Ungültige Spaltenzuordnung: {exc}") from exc

    run = persist_rows(
        db, source_name=source_name, filename=file.filename or "upload.csv",
        rows=rows, normalizer=lambda row: normalize(row, mapping), first_row_number=2,
    )
    return run_as_dict(run)


@app.get("/api/connectors/dummyjson/preview")
def preview_dummyjson():
    try:
        rows = dummyjson.fetch_products()
    except dummyjson.ConnectorError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"source": dummyjson.SOURCE_NAME, "total_rows": len(rows),
            "preview": [{"id": row.get("id"), "title": row.get("title"),
                         "price": row.get("price"), "stock": row.get("stock")} for row in rows[:5]],
            "currency_note": "Die API weist keine verlässliche Währung aus. Preise werden als Demo-Werte ohne Währung gespeichert."}


@app.post("/api/imports/dummyjson")
def import_dummyjson(db: Session = Depends(get_db)):
    try:
        rows = dummyjson.fetch_products()
    except dummyjson.ConnectorError as exc:
        raise HTTPException(502, str(exc)) from exc
    run = persist_rows(
        db, source_name=dummyjson.SOURCE_NAME, filename="dummyjson://products?limit=20",
        rows=rows, normalizer=dummyjson.normalize_product, first_row_number=1,
    )
    return run_as_dict(run)


def run_as_dict(run: ImportRun):
    return {"id": run.id, "source_name": run.source_name, "filename": run.filename,
            "status": run.status, "total_rows": run.total_rows, "inserted": run.inserted,
            "updated": run.updated, "unchanged": run.unchanged, "rejected": run.rejected,
            "created_at": run.created_at.isoformat() if run.created_at else None}


@app.get("/api/imports")
def list_imports(db: Session = Depends(get_db)):
    runs = db.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(30)).all()
    return [run_as_dict(run) for run in runs]


@app.get("/api/imports/{run_id}/issues")
def get_issues(run_id: int, db: Session = Depends(get_db)):
    if db.get(ImportRun, run_id) is None:
        raise HTTPException(404, "Import nicht gefunden")
    issues = db.scalars(select(ValidationIssue).where(ValidationIssue.import_id == run_id).order_by(ValidationIssue.row_number)).all()
    return [{"row_number": i.row_number, "field": i.field, "code": i.code, "message": i.message} for i in issues]


@app.get("/api/offers")
def list_offers(db: Session = Depends(get_db)):
    offers = db.scalars(select(SupplierOffer).order_by(SupplierOffer.id.desc()).limit(100)).all()
    return [{"id": o.id, "source_name": o.source_name, "external_id": o.external_id,
             "name": o.name, "price_amount": str(o.price_amount), "currency": o.currency,
             "stock": o.stock} for o in offers]


# Filter and paginate in the database, not over the first 100 offers in the browser.
CatalogSort = Literal["name_asc", "name_desc", "stock_asc", "stock_desc", "source_asc", "latest"]


def catalog_query(search: str, source: str | None, sort: CatalogSort):
    """One filter / ordering definition for on-screen catalog and CSV export."""
    query = select(SupplierOffer)
    search = search.strip()
    if search:
        literal = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{literal}%"
        query = query.where(or_(
            SupplierOffer.name.ilike(pattern, escape="\\"),
            SupplierOffer.external_id.ilike(pattern, escape="\\"),
        ))
    if source:
        query = query.where(SupplierOffer.source_name == source)
    order = {
        "name_asc": (func.lower(SupplierOffer.name).asc(), SupplierOffer.id.asc()),
        "name_desc": (func.lower(SupplierOffer.name).desc(), SupplierOffer.id.asc()),
        "stock_asc": (SupplierOffer.stock.asc().nulls_last(), SupplierOffer.id.asc()),
        "stock_desc": (SupplierOffer.stock.desc().nulls_last(), SupplierOffer.id.asc()),
        "source_asc": (func.lower(SupplierOffer.source_name).asc(), func.lower(SupplierOffer.name).asc(), SupplierOffer.id.asc()),
        "latest": (SupplierOffer.id.desc(),),
    }[sort]
    return query.order_by(*order)


def csv_safe(value: str) -> str:
    """Prevent spreadsheet formula execution for strings from external sources."""
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


@app.get("/api/catalog/offers")
def search_catalog(
    search: str = Query(default="", max_length=100),
    source: str | None = Query(default=None, min_length=1, max_length=100),
    sort: CatalogSort = "name_asc",
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search across ALL offers with stable ordering and server-side pagination.

    Response includes the complete list of available sources, independent
    of the selected source filter, so the selector never loses its options.
    """
    query = catalog_query(search, source, sort)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offers = db.scalars(query.offset(offset).limit(limit)).all()
    sources = db.scalars(select(SupplierOffer.source_name).distinct().order_by(SupplierOffer.source_name)).all()
    return {
        "total": total, "offset": offset, "limit": limit, "sources": sources,
        "items": [{"id": o.id, "source_name": o.source_name,
                   "external_id": o.external_id, "name": o.name,
                   "price_amount": str(o.price_amount), "currency": o.currency,
                   "stock": o.stock} for o in offers],
    }


@app.get("/api/catalog/export.csv")
def export_catalog_csv(
    search: str = Query(default="", max_length=100),
    source: str | None = Query(default=None, min_length=1, max_length=100),
    sort: CatalogSort = "name_asc",
    db: Session = Depends(get_db),
):
    """Export all filtered results, not only the current page (up to 10k rows).

    UTF-8 BOM + semicolon delimiter makes the export practical in German Excel.
    This deliberately does not export price amounts as EUR if currency is unknown.
    """
    query = catalog_query(search, source, sort)
    count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if count > 10_000:
        raise HTTPException(422, "CSV-Export ist auf 10.000 Treffer begrenzt. Bitte Filter eingrenzen.")
    offers = db.scalars(query).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Produkt", "Externe ID", "Datenquelle", "Preis", "Währung", "Bestand"])
    for offer in offers:
        writer.writerow([
            csv_safe(offer.name), csv_safe(offer.external_id), csv_safe(offer.source_name),
            format(offer.price_amount, ".2f"),
            csv_safe(offer.currency if offer.currency != "XXX" else "Unbekannt"),
            "" if offer.stock is None else str(offer.stock),
        ])
    return Response(
        content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="databridge-catalog.csv"',
                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/summary")
def summary(db: Session = Depends(get_db)):
    return {"offers": db.scalar(select(func.count()).select_from(SupplierOffer)) or 0,
            "imports": db.scalar(select(func.count()).select_from(ImportRun)) or 0,
            "issues": db.scalar(select(func.count()).select_from(ValidationIssue)) or 0,
            "sources": db.scalar(select(func.count(func.distinct(SupplierOffer.source_name)))) or 0}


@app.get("/api/imports/{run_id}/rows")
def import_rows(run_id: int, offset: int = Query(0, ge=0),
                limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    """Inspect original inputs and outcomes, including rejected rows.

    Missing event + no validation issue indicates an import predating v0.3.
    """
    run = db.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(404, "Import nicht gefunden")
    rows = db.scalars(select(SourceRow).where(SourceRow.import_id == run_id)
                      .order_by(SourceRow.row_number).offset(offset).limit(limit)).all()
    row_ids = [row.id for row in rows]
    row_numbers = [row.row_number for row in rows]
    events = db.scalars(select(OfferEvent).where(OfferEvent.source_row_id.in_(row_ids))).all() if row_ids else []
    issues = db.scalars(select(ValidationIssue).where(ValidationIssue.import_id == run_id,
                    ValidationIssue.row_number.in_(row_numbers))).all() if row_numbers else []
    event_by_row = {event.source_row_id: event for event in events}
    issues_by_number: dict[int, list[dict]] = {}
    for issue in issues:
        issues_by_number.setdefault(issue.row_number, []).append({
            "field": issue.field, "code": issue.code, "message": issue.message,
        })
    return {"run": run_as_dict(run), "offset": offset, "limit": limit,
            "rows": [{"row_number": row.row_number, "raw": row.payload,
                      "action": event_by_row[row.id].action if row.id in event_by_row else
                                "rejected" if row.row_number in issues_by_number else "legacy",
                      "offer_id": event_by_row[row.id].offer_id if row.id in event_by_row else None,
                      "normalized": event_by_row[row.id].after if row.id in event_by_row else None,
                      "issues": issues_by_number.get(row.row_number, [])}
                     for row in rows]}


@app.get("/api/offers/{offer_id}/lineage")
def offer_lineage(offer_id: int, db: Session = Depends(get_db)):
    """Explain each accepted decision and expose original payload + changed fields."""
    offer = db.get(SupplierOffer, offer_id)
    if offer is None:
        raise HTTPException(404, "Angebot nicht gefunden")
    events = db.scalars(select(OfferEvent).where(OfferEvent.offer_id == offer_id)
                        .order_by(OfferEvent.id.desc()).limit(100)).all()
    run_ids = {event.import_id for event in events}
    row_ids = {event.source_row_id for event in events}
    runs = {run.id: run for run in db.scalars(select(ImportRun).where(ImportRun.id.in_(run_ids))).all()} if run_ids else {}
    source_rows = {row.id: row for row in db.scalars(select(SourceRow).where(SourceRow.id.in_(row_ids))).all()} if row_ids else {}
    return {
        "offer": {"id": offer.id, "source_name": offer.source_name,
                  **offer_snapshot(offer), "last_changed_import_id": offer.last_import_id},
        "history_available_since": "v0.3",
        "history_limited": len(events) == 100,
        "events": [{
            "id": event.id, "action": event.action,
            "import_id": event.import_id,
            "import_filename": runs[event.import_id].filename,
            "import_created_at": runs[event.import_id].created_at.isoformat(),
            "row_number": source_rows[event.source_row_id].row_number,
            "raw": source_rows[event.source_row_id].payload,
            "before": event.before, "after": event.after,
            "changed_fields": [key for key in event.after
                               if event.before is None or event.before.get(key) != event.after[key]],
        } for event in events],
    }


class ScheduleConfig(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440)


@app.get("/api/pipelines/dummyjson")
def pipeline_status(db: Session = Depends(get_db)):
    schedule = db.scalar(select(PipelineSchedule).where(PipelineSchedule.connector == "dummyjson"))
    return serialize_schedule(schedule)


@app.put("/api/pipelines/dummyjson")
def configure_pipeline(config: ScheduleConfig, db: Session = Depends(get_db)):
    try:
        return update_schedule(db, enabled=config.enabled, interval_minutes=config.interval_minutes)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/pipelines/dummyjson/run-now")
def pipeline_run_now(db: Session = Depends(get_db)):
    """Queue a near-immediate run; worker executes it on its next poll."""
    try:
        return trigger_now(db)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/pipelines/dummyjson/executions")
def pipeline_executions(db: Session = Depends(get_db)):
    schedule = db.scalar(select(PipelineSchedule).where(PipelineSchedule.connector == "dummyjson"))
    if schedule is None:
        return []
    runs = db.scalars(select(PipelineExecution)
                      .where(PipelineExecution.schedule_id == schedule.id)
                      .order_by(PipelineExecution.id.desc()).limit(40)).all()
    return [serialize_execution(run) for run in runs]


@app.get("/api/analytics/quality")
def quality_analytics(
    source: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    """Real measured per-run acceptance rates, with no estimated or invented scores.

    Rejected rows and validation issues are *different* measures: a row may
    contain multiple issues in future versions of the validation engine.
    """
    available_sources = db.scalars(
        select(ImportRun.source_name).distinct().order_by(ImportRun.source_name)
    ).all()
    run_query = select(ImportRun).where(
        ImportRun.status.in_(["completed", "completed_with_issues"])
    )
    if source is not None:
        run_query = run_query.where(ImportRun.source_name == source)
    runs = db.scalars(run_query.order_by(ImportRun.id.desc())).all()
    total_rows = sum(run.total_rows for run in runs)
    rejected = sum(run.rejected for run in runs)
    accepted = total_rows - rejected
    quality_percent = round(100 * accepted / total_rows, 1) if total_rows else None

    group = {}
    for run in runs:
        bucket = group.setdefault(run.source_name, {
            "source_name": run.source_name,
            "runs": 0, "total_rows": 0, "accepted": 0, "rejected": 0,
        })
        bucket["runs"] += 1
        bucket["total_rows"] += run.total_rows
        bucket["accepted"] += run.total_rows - run.rejected
        bucket["rejected"] += run.rejected

    for bucket in group.values():
        bucket["quality_percent"] = (
            round(100 * bucket["accepted"] / bucket["total_rows"], 1)
            if bucket["total_rows"] else None
        )

    issue_stmt = (
        select(ValidationIssue.field, ValidationIssue.code,
               func.count(ValidationIssue.id).label("count"))
        .join(ImportRun, ImportRun.id == ValidationIssue.import_id)
        .where(ImportRun.status.in_(["completed", "completed_with_issues"]))
        .group_by(ValidationIssue.field, ValidationIssue.code)
        .order_by(func.count(ValidationIssue.id).desc())
        .limit(8)
    )
    if source is not None:
        issue_stmt = issue_stmt.where(ImportRun.source_name == source)
    issues = db.execute(issue_stmt).all()

    return {
        "filter_source": source,
        "available_sources": available_sources,
        "total_runs": len(runs),
        "total_rows": total_rows,
        "accepted": accepted,
        "rejected": rejected,
        "quality_percent": quality_percent,
        "by_source": sorted(group.values(), key=lambda item: item["source_name"].lower()),
        "top_issues": [{"field": field, "code": code, "count": count}
                       for field, code, count in issues],
        "recent_runs": [{
            "id": run.id,
            "source_name": run.source_name,
            "total_rows": run.total_rows,
            "accepted": run.total_rows - run.rejected,
            "rejected": run.rejected,
            "quality_percent": (
                round(100 * (run.total_rows - run.rejected) / run.total_rows, 1)
                if run.total_rows else None
            ),
            "created_at": run.created_at.isoformat() if run.created_at else None,
        } for run in runs[:15]],
    }
