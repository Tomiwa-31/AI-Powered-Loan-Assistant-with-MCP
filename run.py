"""
FinScreen — start the web server.
Run: python run.py
Then open: http://localhost:8000
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=False)

#Also note reload=False in run.py — this is required. Hot reload was killing the subprocess connection mid-assessment.
#subprocess and session
