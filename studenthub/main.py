from fastapi import FastAPI
from studenthub.routes import auth, posts
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = FastAPI()

app.include_router(auth.router)
app.include_router(posts.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
