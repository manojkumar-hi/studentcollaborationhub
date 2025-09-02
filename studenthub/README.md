# StudentHub Backend (FastAPI + MongoDB)

## Setup Instructions

1. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your `.env` file with MongoDB and email credentials.
4. Run the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```
5. Test the health endpoint:
   - Open: [http://localhost:8000/health](http://localhost:8000/health)
   - Should return `{ "status": "ok" }`

---

**Pause here and follow your manual setup steps for MongoDB and Thunder Client.**
