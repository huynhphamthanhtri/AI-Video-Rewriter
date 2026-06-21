from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.preset import AppSettingORM


class AppSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        item = self.db.get(AppSettingORM, key)
        if item is None:
            return default
        try:
            return json.loads(item.value_json)
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any) -> Any:
        payload = json.dumps(value, ensure_ascii=False)
        item = self.db.get(AppSettingORM, key)
        now = time.time()
        if item is None:
            item = AppSettingORM(key=key, value_json=payload, updated_at=now)
            self.db.add(item)
        else:
            item.value_json = payload
            item.updated_at = now
        self.db.commit()
        return value

    def delete(self, key: str) -> None:
        item = self.db.get(AppSettingORM, key)
        if item is not None:
            self.db.delete(item)
            self.db.commit()
