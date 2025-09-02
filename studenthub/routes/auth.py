import os
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, File, UploadFile
from fastapi import Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import bcrypt
import jwt
import requests

from ..models.user import UserCreate, UserLogin, UserOut
from ..database import db
from ..utils.otp import generate_otp, get_expiry
from ..utils.mail import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])


# Config/constants
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "dkdqyigl1")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "studenthub_profile")
CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

security = HTTPBearer()


# ----------------- Utility Functions -----------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_doc = db.users_v2.find_one({"email": email})
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")
        return user_doc
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ----------------- SIGNUP & OTP -----------------
class SignupRequest(UserCreate):
    pass


class UserOutWithMsg(UserOut):
    message: str


class EmailOTP(BaseModel):
    email: EmailStr
    otp: str


@router.post("/signup", response_model=UserOutWithMsg)
async def signup(user: SignupRequest, background_tasks: BackgroundTasks):
    if db.users_v2.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pw = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
    otp = generate_otp()
    expiry = get_expiry()

    user_doc = {
        "name": user.name,
        "bio": user.bio,
        "email": user.email,
        "passwordHash": hashed_pw.decode(),
        "profilePic": None,
        "isVerified": False,
        "otp": otp,
        "otpExpiry": expiry
    }
    result = db.users_v2.insert_one(user_doc)
    background_tasks.add_task(send_otp_email, user.email, otp)

    return UserOutWithMsg(
        id=str(result.inserted_id),
        name=user.name,
        bio=user.bio,
        email=user.email,
        isVerified=False,
        profilePic=None,
        message="Signup successful. OTP sent to email."
    )


@router.post("/verify-email")
def verify_email(data: EmailOTP):
    user_doc = db.users_v2.find_one({"email": data.email})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    if user_doc.get("isVerified"):
        return {"message": "Already verified"}
    if user_doc.get("otp") != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if user_doc.get("otpExpiry") and user_doc["otpExpiry"] < get_expiry(0):
        raise HTTPException(status_code=400, detail="OTP expired")

    db.users_v2.update_one(
        {"email": data.email},
        {"$set": {"isVerified": True, "otp": None, "otpExpiry": None}}
    )
    return {"message": "Email verified successfully"}


# ----------------- LOGIN -----------------
@router.post("/login")
def login(user: UserLogin):
    user_doc = db.users_v2.find_one({"email": user.email})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bcrypt.checkpw(user.password.encode(), user_doc["passwordHash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user_doc.get("isVerified", False):
        raise HTTPException(status_code=403, detail="Email not verified. Please verify your email before logging in.")

    payload = {
        "sub": user_doc["email"],
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user_doc["_id"]),
            "name": user_doc["name"],
            "bio": user_doc.get("bio", ""),
            "email": user_doc["email"],
            "isVerified": user_doc.get("isVerified", False),
            "profilePic": user_doc.get("profilePic")
        }
    }


# ----------------- PROFILE MODULE -----------------
@router.get("/profile", response_model=UserOut)
def get_profile(current_user: dict = Depends(get_current_user)):
    return UserOut(
        id=str(current_user["_id"]),
        name=current_user["name"],
        bio=current_user.get("bio", ""),
        email=current_user["email"],
        isVerified=current_user.get("isVerified", False),
        profilePic=current_user.get("profilePic")
    )


@router.put("/profile/update", response_model=UserOut)
async def update_profile(
    name: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    update_data = {}
    if name:
        update_data["name"] = name
    if bio:
        update_data["bio"] = bio

    if file:
        # Debug: print env vars
        print("CLOUDINARY_CLOUD_NAME:", CLOUDINARY_CLOUD_NAME)
        print("CLOUDINARY_UPLOAD_PRESET:", CLOUDINARY_UPLOAD_PRESET)
        print("CLOUDINARY_UPLOAD_URL:", CLOUDINARY_UPLOAD_URL)
        # Validate image type
        if file.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(status_code=400, detail="Only JPEG or PNG images allowed")
        files = {"file": (file.filename, file.file, file.content_type)}
        data = {"upload_preset": CLOUDINARY_UPLOAD_PRESET}
        try:
            resp = requests.post(CLOUDINARY_UPLOAD_URL, files=files, data=data)
            print("Cloudinary status:", resp.status_code)
            print("Cloudinary response:", resp.text)
            resp.raise_for_status()
            update_data["profilePic"] = resp.json().get("secure_url")
        except Exception as e:
            print("Cloudinary upload error:", str(e))
            raise HTTPException(status_code=500, detail="Profile picture upload failed")

    if update_data:
        db.users_v2.update_one({"_id": current_user["_id"]}, {"$set": update_data})

    user_doc = db.users_v2.find_one({"_id": current_user["_id"]})
    return UserOut(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        bio=user_doc.get("bio", ""),
        email=user_doc["email"],
        isVerified=user_doc.get("isVerified", False),
        profilePic=user_doc.get("profilePic")
    )
