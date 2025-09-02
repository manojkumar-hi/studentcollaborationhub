from dotenv import load_dotenv
import os
from pymongo import MongoClient

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "studenthub_v2")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

print("DEBUG: MONGO_URI =", MONGO_URI)
print("DEBUG: DB_NAME =", DB_NAME)
