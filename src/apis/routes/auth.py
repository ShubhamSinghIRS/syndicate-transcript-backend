from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from apis.controllers.auth import auth_controller
from apis.controllers.auth.auth_schema import (
    AuthResponse,
    AuthSessionResponse,
    ForgotPasswordRequest,
    LoginOtpSendRequest,
    LoginOtpVerifyRequest,
    LoginRequest,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    VerifyOtpRequest,
)
from apis.rate_limiting.dependencies import (
    rate_limit_forgot_password,
    rate_limit_login,
    rate_limit_login_otp_send,
    rate_limit_login_otp_verify,
    rate_limit_register,
    rate_limit_register_otp_verify,
    rate_limit_resend_otp,
)
from config import get_settings
from utils.cookies import (
    REFRESH_COOKIE_NAME,
    clear_access_cookie,
    clear_refresh_cookie,
    set_access_cookie,
    set_refresh_cookie,
)
from utils.csrf import verify_same_origin
from utils.request_meta import get_device_info, get_ip_address
from utils.response import success_response

from .paths import P

router = APIRouter(prefix=P.auth.BASE, tags=["Auth"])


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    auth_settings = get_settings().auth
    set_refresh_cookie(
        response, raw_token, auth_settings.cookie_secure, auth_settings.refresh_token_expiry_days, P.auth.BASE
    )


def _set_access_cookie(response: Response, token: str) -> None:
    auth_settings = get_settings().auth
    set_access_cookie(response, token, auth_settings.cookie_secure, auth_settings.access_token_expiry_minutes)


def _session_response(auth_response: AuthResponse) -> AuthSessionResponse:
    # The token was just minted in this same request, so its lifetime is
    # exactly the configured expiry from now - no need to decode it back out.
    expiry_minutes = get_settings().auth.access_token_expiry_minutes
    return AuthSessionResponse(user=auth_response.user, accessTokenExpiresIn=expiry_minutes * 60)


@router.post(P.auth.REGISTER, dependencies=[Depends(rate_limit_register)])
def register(data: RegisterRequest, background_tasks: BackgroundTasks):
    result = auth_controller.register(data, background_tasks)
    return success_response(data=result, message="OTP sent to your email. Please verify to complete registration.")


@router.post(P.auth.REGISTER_VERIFY_OTP, dependencies=[Depends(rate_limit_register_otp_verify)])
def verify_registration_otp(data: VerifyOtpRequest, request: Request, response: Response):
    auth_response, raw_refresh_token = auth_controller.verify_registration_otp(
        data, get_device_info(request), get_ip_address(request)
    )
    _set_refresh_cookie(response, raw_refresh_token)
    _set_access_cookie(response, auth_response.token)
    return success_response(data=_session_response(auth_response), message="Registration successful.")


@router.post(P.auth.REGISTER_RESEND_OTP, dependencies=[Depends(rate_limit_resend_otp)])
def resend_otp(data: ResendOtpRequest, background_tasks: BackgroundTasks):
    result = auth_controller.resend_otp(data, background_tasks)
    return success_response(data=result, message="A new OTP has been sent to your email.")


@router.post(P.auth.LOGIN, dependencies=[Depends(rate_limit_login)])
def login(data: LoginRequest, request: Request, response: Response):
    auth_response, raw_refresh_token = auth_controller.login(data, get_device_info(request), get_ip_address(request))
    _set_refresh_cookie(response, raw_refresh_token)
    _set_access_cookie(response, auth_response.token)
    return success_response(data=_session_response(auth_response), message="Login successful.")


@router.post(P.auth.LOGIN_OTP_SEND, dependencies=[Depends(rate_limit_login_otp_send)])
def send_login_otp(data: LoginOtpSendRequest, background_tasks: BackgroundTasks):
    result = auth_controller.send_login_otp(data, background_tasks)
    return success_response(data=result, message="OTP sent to your email.")


@router.post(P.auth.LOGIN_OTP_VERIFY, dependencies=[Depends(rate_limit_login_otp_verify)])
def verify_login_otp(data: LoginOtpVerifyRequest, request: Request, response: Response):
    auth_response, raw_refresh_token = auth_controller.verify_login_otp(
        data, get_device_info(request), get_ip_address(request)
    )
    _set_refresh_cookie(response, raw_refresh_token)
    _set_access_cookie(response, auth_response.token)
    return success_response(data=_session_response(auth_response), message="Login successful.")


@router.post(P.auth.REFRESH)
def refresh(request: Request, response: Response):
    verify_same_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    auth_response, new_raw_refresh_token = auth_controller.refresh(
        raw_token, get_device_info(request), get_ip_address(request)
    )
    _set_refresh_cookie(response, new_raw_refresh_token)
    _set_access_cookie(response, auth_response.token)
    return success_response(data=_session_response(auth_response), message="Token refreshed.")


@router.post(P.auth.FORGOT_PASSWORD, dependencies=[Depends(rate_limit_forgot_password)])
def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    auth_controller.forgot_password(data, background_tasks)
    return success_response(message="Password reset link has been sent to your email.")


@router.post(P.auth.RESET_PASSWORD)
def reset_password(data: ResetPasswordRequest, response: Response):
    auth_controller.reset_password(data)
    # All other sessions were just revoked server-side (handle_reset_password) -
    # also drop this browser's own cookies so it doesn't keep looking logged in.
    clear_refresh_cookie(response, get_settings().auth.cookie_secure, P.auth.BASE)
    clear_access_cookie(response, get_settings().auth.cookie_secure)
    return success_response(message="Password reset successful.")


@router.post(P.auth.LOGOUT)
def logout(request: Request, response: Response):
    verify_same_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    auth_controller.logout(raw_token)
    clear_refresh_cookie(response, get_settings().auth.cookie_secure, P.auth.BASE)
    clear_access_cookie(response, get_settings().auth.cookie_secure)
    return success_response(message="Logged out successfully.")
