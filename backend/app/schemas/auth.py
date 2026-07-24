from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4)
    role: str = Field(pattern="^(user|admin)$")


class PasswordChange(BaseModel):
    username: str
    new_password: str = Field(min_length=4)
