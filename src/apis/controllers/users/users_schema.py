from pydantic import BaseModel


class ProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    companyName: str | None = None
    # Seconds left on the access token that authenticated this request - lets
    # the frontend schedule its next proactive refresh without ever reading
    # the (httpOnly, JS-inaccessible) token itself.
    accessTokenExpiresIn: int
