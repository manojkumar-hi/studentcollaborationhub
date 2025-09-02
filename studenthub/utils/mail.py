from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

import os
print("DEBUG: MAIL_PORT from env:", os.getenv("MAIL_PORT"))

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", "test@example.com"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", "password"),
    MAIL_FROM=os.getenv("MAIL_FROM", "test@example.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.example.com"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)

async def send_otp_email(email: str, otp: str):
    message = MessageSchema(
        subject="StudentHub Email Verification OTP",
        recipients=[email],
        body=f"Your OTP for StudentHub is: {otp}",
        subtype="plain"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
