import os
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, File, UploadFile, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import bcrypt
import jwt
import requests
import asyncio

from ..models.user import UserCreate, UserLogin, UserOut
from ..database import db
from ..utils.otp import generate_otp
from ..utils.mail import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Config/constants
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "dkdqyigl1")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "studenthub_profile")
CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

security = HTTPBearer()

# ----------------- OTP EXPIRY CONFIG -----------------
OTP_EXPIRY_SECONDS = 300  # 5 minutes
otp_store = {}  # {email: {"otp": "123456", "expiry": datetime, "user_data": {...}}}

# ----------------- UTILITY -----------------
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

# ----------------- OTP EXPIRY HANDLER -----------------
async def remove_otp_after_expiry(email: str, delay: int = OTP_EXPIRY_SECONDS):
    await asyncio.sleep(delay)
    if email in otp_store:
        del otp_store[email]
        print(f"DEBUG: OTP for {email} expired and removed from memory.")

@router.post("/signup")
async def signup(user: SignupRequest, background_tasks: BackgroundTasks):
    if db.users_v2.find_one({"email": user.email}) or user.email in otp_store:
        raise HTTPException(status_code=400, detail="Email already registered or pending verification")

    hashed_pw = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
    otp = generate_otp()

    user_data = {
        "name": user.name,
        "bio": user.bio,
        "email": user.email,
        "passwordHash": hashed_pw.decode(),
        "profilePic": None,
        "isVerified": False
    }

    expiry_time = datetime.utcnow() + timedelta(seconds=OTP_EXPIRY_SECONDS)
    otp_store[user.email] = {"otp": otp, "expiry": expiry_time, "user_data": user_data}

    async def send_otp_task(email, otp):
        print(f"DEBUG: Sending OTP {otp} to {email}")
        await send_otp_email(email, otp)
        print(f"DEBUG: OTP sent to {email}")

    background_tasks.add_task(send_otp_task, user.email, otp)
    background_tasks.add_task(remove_otp_after_expiry, user.email)

    return {
        "message": "Signup initiated. OTP sent to email.",
        "expires_at": expiry_time.isoformat()
    }

@router.post("/verify-email")
def verify_email(data: EmailOTP):
    record = otp_store.get(data.email)
    if not record:
        raise HTTPException(status_code=404, detail="No signup found for this email or OTP expired")
    
    if record["otp"] != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if record["expiry"] < datetime.utcnow():
        del otp_store[data.email]
        raise HTTPException(status_code=400, detail="OTP expired")
    
    result = db.users_v2.insert_one(record["user_data"])
    del otp_store[data.email]

    return {"message": "Email verified successfully. Signup complete.", "user_id": str(result.inserted_id)}

# ----------------- LOGIN -----------------
@router.post("/login")
def login(user: UserLogin):
    user_doc = db.users_v2.find_one({"email": user.email})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bcrypt.checkpw(user.password.encode(), user_doc["passwordHash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

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
        if file.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(status_code=400, detail="Only JPEG or PNG images allowed")
        files = {"file": (file.filename, file.file, file.content_type)}
        data = {"upload_preset": CLOUDINARY_UPLOAD_PRESET}
        try:
            resp = requests.post(CLOUDINARY_UPLOAD_URL, files=files, data=data)
            resp.raise_for_status()
            update_data["profilePic"] = resp.json().get("secure_url")
        except Exception:
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

@router.put("/profile/remove-pic", response_model=UserOut)
def remove_profile_pic(current_user: dict = Depends(get_current_user)):
    db.users_v2.update_one({"_id": current_user["_id"]}, {"$set": {"profilePic": None}})
    user_doc = db.users_v2.find_one({"_id": current_user["_id"]})
    return UserOut(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        bio=user_doc.get("bio", ""),
        email=user_doc["email"],
        isVerified=user_doc.get("isVerified", False),
        profilePic=user_doc.get("profilePic")
    )
