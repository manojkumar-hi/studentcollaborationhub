from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, Body
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from ..database import db
from ..models.post import PostCreate, PostOut, Comment
from ..models.user import UserOut
from bson.objectid import ObjectId
import requests
import os
from .auth import get_current_user

# Cloudinary config from .env
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "dkdqyigl1")
CLOUDINARY_UPLOAD_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "studenthub_profile")
CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"

router = APIRouter(prefix="/posts", tags=["posts"])

# --- Like/Unlike Posts ---
@router.post("/{post_id}/like")
def like_post(post_id: str, current_user: dict = Depends(get_current_user)):
    post = db.posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if "likes" not in post:
        post["likes"] = []
    if str(current_user["_id"]) in post["likes"]:
        return {"message": "Already liked"}
    db.posts.update_one({"_id": ObjectId(post_id)}, {"$addToSet": {"likes": str(current_user["_id"])}})
    return {"message": "Post liked"}

@router.post("/{post_id}/unlike")
def unlike_post(post_id: str, current_user: dict = Depends(get_current_user)):
    post = db.posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.posts.update_one({"_id": ObjectId(post_id)}, {"$pull": {"likes": str(current_user["_id"])}})
    return {"message": "Post unliked"}

# --- Post Deletion ---
@router.delete("/{post_id}")
def delete_post(post_id: str, current_user: dict = Depends(get_current_user)):
    post = db.posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if str(post["user_id"]) != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")
    db.posts.delete_one({"_id": ObjectId(post_id)})
    return {"message": "Post deleted successfully"}

@router.post("/", response_model=PostOut)
async def create_post(
    content: str = Form(...),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    image_url = None
    if file:
        if file.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(status_code=400, detail="Only JPEG or PNG images allowed")
        files = {"file": (file.filename, await file.read(), file.content_type)}
        data = {"upload_preset": CLOUDINARY_UPLOAD_PRESET}
        try:
            resp = requests.post(CLOUDINARY_UPLOAD_URL, files=files, data=data)
            resp.raise_for_status()
            image_url = resp.json().get("secure_url")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
    post_doc = {
        "user_id": str(current_user["_id"]),
        "user_name": current_user["name"],
        "user_profilePic": current_user.get("profilePic"),
        "content": content,
        "image": image_url,
        "created_at": datetime.utcnow(),
        "comments": []
    }
    result = db.posts.insert_one(post_doc)
    post_doc["_id"] = result.inserted_id
    return PostOut(
        id=str(post_doc["_id"]),
        user_id=post_doc["user_id"],
        user_name=post_doc["user_name"],
        user_profilePic=post_doc["user_profilePic"],
        content=post_doc["content"],
        image=post_doc["image"],
        created_at=post_doc["created_at"],
        comments=[]
    )

@router.get("/", response_model=List[PostOut])
def get_posts():
    posts = list(db.posts.find().sort("created_at", -1))
    result = []
    for post in posts:
        like_count = len(post.get("likes", []))
        # Optionally, get current user from request context if available
        result.append({
            "id": str(post["_id"]),
            "user_id": post["user_id"],
            "user_name": post["user_name"],
            "user_profilePic": post.get("user_profilePic"),
            "content": post["content"],
            "image": post.get("image"),
            "created_at": post["created_at"],
            "comments": [Comment(**c) for c in post.get("comments", [])],
            "like_count": like_count,
            # "liked_by_current_user": ... (frontend can check this if needed)
        })
    return result

from fastapi import Body

class CommentBody(BaseModel):
    text: str

@router.post("/{post_id}/comment", response_model=PostOut)
async def add_comment(
    post_id: str,
    body: CommentBody = Body(...),
    current_user: dict = Depends(get_current_user)
):
    comment = Comment(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        text=body.text
    ).dict()
    db.posts.update_one({"_id": ObjectId(post_id)}, {"$push": {"comments": comment}})
    post = db.posts.find_one({"_id": ObjectId(post_id)})
    return PostOut(
        id=str(post["_id"]),
        user_id=post["user_id"],
        user_name=post["user_name"],
        user_profilePic=post.get("user_profilePic"),
        content=post["content"],
        image=post.get("image"),
        created_at=post["created_at"],
        comments=[Comment(**c) for c in post.get("comments", [])]
    )

# --- Delete Comment ---
@router.delete("/{post_id}/comment/{comment_index}")
def delete_comment(post_id: str, comment_index: int, current_user: dict = Depends(get_current_user)):
    post = db.posts.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = post.get("comments", [])
    if comment_index < 0 or comment_index >= len(comments):
        raise HTTPException(status_code=404, detail="Comment not found")
    # Only allow the comment's author to delete
    if str(comments[comment_index]["user_id"]) != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")
    comments.pop(comment_index)
    db.posts.update_one({"_id": ObjectId(post_id)}, {"$set": {"comments": comments}})
    return {"message": "Comment deleted successfully"}
