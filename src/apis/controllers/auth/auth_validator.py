from fastapi import HTTPException

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt silently truncates beyond this - reject rather than accept dead weight

# Not exhaustive - a cheap denylist for the most egregiously common passwords,
# not a substitute for a full breach-corpus check (e.g. HaveIBeenPwned's
# range API). Catches the passwords that would fall on the first try of any
# credential-stuffing list.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789", "12345678",
    "1234567890", "qwertyuiop", "letmein123", "welcome123", "iloveyou",
    "administrator", "changeme", "passw0rd", "abc123456", "qwerty123",
}


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() in _COMMON_PASSWORDS:
        raise HTTPException(status_code=400, detail="This password is too common. Please choose another.")


def validate_otp_format(otp: str) -> None:
    if not otp or not otp.isdigit() or len(otp) != 6:
        raise HTTPException(status_code=400, detail="Invalid OTP format.")
