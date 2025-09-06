from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, message, ws  # add ws
# from app.database import Base, engine   # if you were creating tables here

app = FastAPI()

# Optional CORS (helpful if you’re testing from a web page)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(message.router)  # your REST chat endpoints
app.include_router(ws.router)       # ✅ WebSocket endpoints
