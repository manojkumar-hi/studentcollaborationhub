from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Comment(BaseModel):
    user_id: str
    user_name: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PostCreate(BaseModel):
    content: str
    image: Optional[str] = None

class PostOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_profilePic: Optional[str] = None
    content: str
    image: Optional[str] = None
    created_at: datetime
    comments: List[Comment] = []
    likes: List[str] = []  # Add likes field for frontend
