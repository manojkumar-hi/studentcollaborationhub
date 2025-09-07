
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from studenthub.routes import auth, posts
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = FastAPI()

# Allow your frontend origin
origins = [
    "http://localhost:5173",  # your React dev server
    "https://studentcollaborationhub.onrender.com", # deployed frontend
    "https://studentcollaborationhub.onrender.com/", # with trailing slash
    "https://studentcollaborationhub.onrender.com/profile", # profile route
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,     # allow requests from this origin
    allow_credentials=True,
    allow_methods=["*"],       # allow all HTTP methods
    allow_headers=["*"],       # allow all headers
)

app.include_router(auth.router)
app.include_router(posts.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
