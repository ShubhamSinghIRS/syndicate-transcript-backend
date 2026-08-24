from pydantic import BaseModel, EmailStr, Field

# Upper bounds only - reject oversized payloads before they're hashed/compared.
# Actual business rules (min password length, common-password denylist, exact
# OTP format) still live in auth_validator.py and run after this.
_EMAIL_MAX_LENGTH = 254  # RFC 5321 max mailbox length
_PASSWORD_MAX_LENGTH = 124
_NAME_MAX_LENGTH = 200
_COMPANY_NAME_MAX_LENGTH = 500
_OTP_MAX_LENGTH = 6  # OTPs are always exactly 6 digits
_TEMP_TOKEN_MAX_LENGTH = 512  # purpose JWTs measure ~235 chars in practice


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=_NAME_MAX_LENGTH)
    email: EmailStr = Field(max_length=_EMAIL_MAX_LENGTH)
    password: str = Field(max_length=_PASSWORD_MAX_LENGTH)
    companyName: str | None = Field(default=None, max_length=_COMPANY_NAME_MAX_LENGTH)


class PendingAuthResponse(BaseModel):
    tempToken: str


class VerifyOtpRequest(BaseModel):
    tempToken: str = Field(max_length=_TEMP_TOKEN_MAX_LENGTH)
    otp: str = Field(max_length=_OTP_MAX_LENGTH)


class ResendOtpRequest(BaseModel):
    tempToken: str = Field(max_length=_TEMP_TOKEN_MAX_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LENGTH)
    password: str = Field(max_length=_PASSWORD_MAX_LENGTH)


class LoginOtpSendRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LENGTH)


class LoginOtpVerifyRequest(BaseModel):
    tempToken: str = Field(max_length=_TEMP_TOKEN_MAX_LENGTH)
    otp: str = Field(max_length=_OTP_MAX_LENGTH)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LENGTH)


class ResetPasswordRequest(BaseModel):
    token: str = Field(max_length=_TEMP_TOKEN_MAX_LENGTH)
    password: str = Field(max_length=_PASSWORD_MAX_LENGTH)


class AuthUserResponse(BaseModel):
    id: str
    name: str
    email: str
    companyName: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: AuthUserResponse
