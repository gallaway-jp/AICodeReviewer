from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI()
INVITATIONS = []


class InvitationRequest(BaseModel):
    email: str
    role: str


@app.get("/api/invitations/create")
def create_invitation(payload: InvitationRequest):
    invitation = {
        "id": len(INVITATIONS) + 1,
        "email": payload.email,
        "role": payload.role,
    }
    INVITATIONS.append(invitation)
    return invitation
