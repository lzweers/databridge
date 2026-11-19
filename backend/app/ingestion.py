"""CSV/API ingestion with durable, per-row provenance events.

SourceRow is the exact original payload. OfferEvent captures validated post-
normalization snapshots and the before/after state; SupplierOffer is the latest
materialized state, unique by (source_name, external_id).
"""
from collections.abc import Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from .models import ImportRun, SourceRow, SupplierOffer, ValidationIssue, OfferEvent
from .parsing import OfferData, issue_for_error


def offer_snapshot(offer: SupplierOffer) -> dict:
    return {
        "external_id": offer.external_id,
        "name": offer.name,
        "price_amount": str(offer.price_amount),
        "currency": offer.currency,
        "stock": offer.stock,
    }


def persist_rows(
    db: Session,
    *,
    source_name: str,
    filename: str,
    rows: list[dict],
    normalizer: Callable[[dict], OfferData],
    first_row_number: int,
) -> ImportRun:
    run = ImportRun(source_name=source_name, filename=filename[:255], total_rows=len(rows))
    try:
        db.add(run)
        db.flush()
        seen_keys: set[str] = set()
        for row_num, row in enumerate(rows, start=first_row_number):
            source_row = SourceRow(import_id=run.id, row_number=row_num, payload=row)
            db.add(source_row)
            db.flush()  # Obtain stable FK for the lineage event.
            try:
                data = normalizer(row)
                if data.external_id in seen_keys:
                    raise ValueError("Produkt-ID kommt innerhalb dieses Imports mehrfach vor.")
                seen_keys.add(data.external_id)
            except (ValidationError, ValueError, TypeError) as exc:
                field, code, message = issue_for_error(exc)
                db.add(ValidationIssue(import_id=run.id, row_number=row_num,
                                       field=field, code=code, message=message))
                run.rejected += 1
                continue

            after = data.model_dump(mode="json")  # Decimal -> lossless string.
            offer = db.scalar(select(SupplierOffer).where(
                SupplierOffer.source_name == source_name,
                SupplierOffer.external_id == data.external_id,
            ))
            before = None
            if offer is None:
                offer = SupplierOffer(
                    source_name=source_name, external_id=data.external_id, name=data.name,
                    price_amount=data.price_amount, currency=data.currency,
                    stock=data.stock, last_import_id=run.id,
                )
                db.add(offer)
                db.flush()
                action = "inserted"
                run.inserted += 1
            else:
                before = offer_snapshot(offer)
                if (offer.name, offer.price_amount, offer.currency, offer.stock) == (
                    data.name, data.price_amount, data.currency, data.stock
                ):
                    action = "unchanged"
                    run.unchanged += 1
                else:
                    offer.name = data.name
                    offer.price_amount = data.price_amount
                    offer.currency = data.currency
                    offer.stock = data.stock
                    offer.last_import_id = run.id
                    action = "updated"
                    run.updated += 1

            db.add(OfferEvent(
                import_id=run.id, source_row_id=source_row.id,
                offer_id=offer.id, action=action, before=before, after=after,
            ))
        run.status = "completed_with_issues" if run.rejected else "completed"
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        raise
