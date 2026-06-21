from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.preset_service import PresetService


def get_preset_service(db: Session = Depends(get_db)) -> PresetService:
    return PresetService(db)
