from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI()
USER_SETTINGS = {
    7: {
        "email_notifications": True,
        "timezone": "UTC",
        "language": "en",
    }
}


class SettingsPatchRequest(BaseModel):
    email_notifications: bool | None = None
    timezone: str | None = None
    language: str | None = None


@app.patch("/api/users/{user_id}/settings")
def patch_user_settings(user_id: int, payload: SettingsPatchRequest):
    USER_SETTINGS[user_id] = payload.model_dump()
    return USER_SETTINGS[user_id]