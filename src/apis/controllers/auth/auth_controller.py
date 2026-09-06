from fastapi import BackgroundTasks

from .auth_handler import (
    handle_forgot_password,
    handle_login,
    handle_logout,
    handle_refresh,
    handle_register,
    handle_resend_otp,
    handle_reset_password,
    handle_send_login_otp,
    handle_verify_login_otp,
    handle_verify_registration_otp,
)
from .auth_schema import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginOtpSendRequest,
    LoginOtpVerifyRequest,
    LoginRequest,
    PendingAuthResponse,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    VerifyOtpRequest,
)
from .auth_validator import validate_otp_format, validate_password


def register(data: RegisterRequest, background_tasks: BackgroundTasks) -> PendingAuthResponse:
    validate_password(data.password)
    return handle_register(data, background_tasks)


def verify_registration_otp(
    data: VerifyOtpRequest, device_info: str | None, ip_address: str | None
) -> tuple[AuthResponse, str]:
    validate_otp_format(data.otp)
    return handle_verify_registration_otp(data.tempToken, data.otp, device_info, ip_address)


def resend_otp(data: ResendOtpRequest, background_tasks: BackgroundTasks) -> PendingAuthResponse:
    return handle_resend_otp(data.tempToken, background_tasks)


def login(data: LoginRequest, device_info: str | None, ip_address: str | None) -> tuple[AuthResponse, str]:
    return handle_login(data.email, data.password, device_info, ip_address)


def send_login_otp(data: LoginOtpSendRequest, background_tasks: BackgroundTasks) -> PendingAuthResponse:
    return handle_send_login_otp(data.email, background_tasks)


def verify_login_otp(
    data: LoginOtpVerifyRequest, device_info: str | None, ip_address: str | None
) -> tuple[AuthResponse, str]:
    validate_otp_format(data.otp)
    return handle_verify_login_otp(data.tempToken, data.otp, device_info, ip_address)


def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks) -> None:
    handle_forgot_password(data.email, background_tasks)


def reset_password(data: ResetPasswordRequest) -> None:
    validate_password(data.password)
    handle_reset_password(data.token, data.password)


def refresh(raw_token: str, device_info: str | None, ip_address: str | None) -> tuple[AuthResponse, str]:
    return handle_refresh(raw_token, device_info, ip_address)


def logout(raw_refresh_token: str | None) -> None:
    handle_logout(raw_refresh_token)
