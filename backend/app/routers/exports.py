from __future__ import annotations

import csv
import io
import json
import zipfile

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import session_dependency
from ..models import Brew, Coffee, Profile, Rating
from ..security import require_admin

router = APIRouter()


def export_rows(db: Session) -> dict[str, list[dict]]:
    coffees = [
        {
            "id": item.id,
            "roaster": item.roaster,
            "name": item.name,
            "country": item.country,
            "region": item.region,
            "producer": item.producer,
            "purchase_location": item.purchase_location,
            "process": item.process,
            "roast_level": item.roast_level,
            "roast_date": item.roast_date,
            "opened_date": item.opened_date,
            "variety": item.variety,
            "package_notes": item.package_notes,
            "chart_color": item.chart_color,
            "finished_at": item.finished_at,
            "archived": item.archived,
        }
        for item in db.scalars(select(Coffee).order_by(Coffee.id))
    ]
    brews = []
    for item in db.scalars(select(Brew).order_by(Brew.id)):
        brews.append(
            {
                "id": item.id,
                "coffee_id": item.coffee_id,
                "operator_id": item.operator_id,
                "grinder_id": item.grinder_id,
                "dripper_id": item.dripper_id,
                "filter_id": item.filter_id,
                "dose_g": item.dose_g,
                "water_g": item.water_g,
                "ratio": round(item.water_g / item.dose_g, 2),
                "target_ratio": item.target_ratio,
                "temperature_c": item.temperature_c,
                "grinder_setting": item.grinder_setting,
                "servings": item.servings,
                "target_flow_g_s": item.target_flow_g_s,
                "total_brew_time_s": item.total_brew_time_s,
                "bloom_water_g": item.bloom_water_g,
                "bloom_time_s": item.bloom_time_s,
                "pour_count": item.pour_count,
                "technique_note": item.technique_note,
                "status": item.status,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
        )
    ratings = []
    for item in db.scalars(
        select(Rating).options(selectinload(Rating.flavor_tags)).order_by(Rating.id)
    ):
        ratings.append(
            {
                "id": item.id,
                "brew_id": item.brew_id,
                "profile_id": item.profile_id,
                "liking": item.liking,
                "acidity": item.acidity,
                "bitterness": item.bitterness,
                "sweetness": item.sweetness,
                "body": item.body,
                "flavor_tags": "; ".join(tag.name for tag in item.flavor_tags),
                "created_at": item.created_at,
            }
        )
    return {"coffees": coffees, "brews": brews, "ratings": ratings}


@router.get("/exports/json")
def export_json(
    db: Session = Depends(session_dependency), _admin: Profile = Depends(require_admin)
) -> JSONResponse:
    return JSONResponse(
        content=json.loads(json.dumps(export_rows(db), default=str)),
        headers={"Content-Disposition": "attachment; filename=fcc-export.json"},
    )


@router.get("/exports/csv")
def export_csv(
    db: Session = Depends(session_dependency), _admin: Profile = Depends(require_admin)
) -> StreamingResponse:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for name, rows in export_rows(db).items():
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            zip_file.writestr(f"{name}.csv", output.getvalue())
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=fcc-csv-export.zip"},
    )
