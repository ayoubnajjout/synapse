from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import PROVIDERS, preferences, provider_views, save_setting
from ..database import get_db
from ..schemas import SettingsPatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return {"preferences": preferences(db), "providers": provider_views(db)}


@router.patch("")
def update_settings(body: SettingsPatch, db: Session = Depends(get_db)):
    if body.providers:
        for name, config in body.providers.items():
            if name not in PROVIDERS:
                raise HTTPException(422, "Unknown provider")
            if config.default_model and config.default_model not in config.models:
                raise HTTPException(422, "Default model must be in the model list")
        for name, config in body.providers.items():
            save_setting(db, f"provider:{name}", config.model_dump())
    if body.preferences:
        merged = {**preferences(db).model_dump(), **body.preferences.model_dump(exclude_unset=True)}
        save_setting(db, "preferences", merged)
    db.commit()
    return get_settings(db)
