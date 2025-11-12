import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from database import create_document, get_documents, db
from schemas import Song as SongSchema, Playlist as PlaylistSchema, Channel as ChannelSchema

app = FastAPI(title="Vibe Music API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Vibe Music API running"}

# ---------- SONGS ----------
class SongCreate(BaseModel):
    title: str
    artist: str
    album: Optional[str] = None
    cover_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration_sec: Optional[int] = None
    genre: Optional[str] = None

@app.get("/api/songs")
def list_songs(query: Optional[str] = None, genre: Optional[str] = None, limit: int = 50):
    try:
        filter_q: Dict[str, Any] = {}
        if query:
            # Simple case-insensitive search across title and artist
            filter_q = {
                "$or": [
                    {"title": {"$regex": query, "$options": "i"}},
                    {"artist": {"$regex": query, "$options": "i"}},
                ]
            }
        if genre:
            filter_q["genre"] = {"$regex": f"^{genre}$", "$options": "i"}
        docs = get_documents("song", filter_q, limit)
        # Convert ObjectId to str if present
        for d in docs:
            if "_id" in d:
                d["id"] = str(d["_id"])
                del d["_id"]
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/songs")
def create_song(payload: SongCreate):
    try:
        song = SongSchema(**payload.model_dump())
        new_id = create_document("song", song)
        return {"id": new_id, "message": "Song added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- PLAYLISTS ----------
class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None

class PlaylistAddSong(BaseModel):
    playlist_id: str
    song_id: str

@app.get("/api/playlists")
def list_playlists(limit: int = 50):
    try:
        docs = get_documents("playlist", {}, limit)
        for d in docs:
            if "_id" in d:
                d["id"] = str(d["_id"])
                del d["_id"]
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playlists")
def create_playlist(payload: PlaylistCreate):
    try:
        playlist = PlaylistSchema(name=payload.name, description=payload.description, song_ids=[])
        new_id = create_document("playlist", playlist)
        return {"id": new_id, "message": "Playlist created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playlists/add")
def add_song_to_playlist(payload: PlaylistAddSong):
    try:
        if db is None:
            raise Exception("Database not available")
        db["playlist"].update_one({"_id": {"$eq": db["playlist"].find_one({"_id": {"$exists": True}, "_id": {"$type": "objectId"}}) }}, {})
        # Simpler: find by string id match stored in a custom field 'id' or fallback to ObjectId string compare
        from bson import ObjectId
        try:
            oid = ObjectId(payload.playlist_id)
            db["playlist"].update_one({"_id": oid}, {"$addToSet": {"song_ids": payload.song_id}})
        except Exception:
            # If playlist_id isn't a valid ObjectId, try match via stored string 'id' field (if any)
            db["playlist"].update_one({"id": payload.playlist_id}, {"$addToSet": {"song_ids": payload.song_id}})
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- CHANNELS (FM) ----------
class ChannelCreate(BaseModel):
    name: str
    description: Optional[str] = None
    stream_url: str
    genre: Optional[str] = None

@app.get("/api/channels")
def list_channels(genre: Optional[str] = None, limit: int = 50):
    try:
        filter_q: Dict[str, Any] = {}
        if genre:
            filter_q["genre"] = {"$regex": f"^{genre}$", "$options": "i"}
        docs = get_documents("channel", filter_q, limit)
        for d in docs:
            if "_id" in d:
                d["id"] = str(d["_id"])
                del d["_id"]
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/channels")
def create_channel(payload: ChannelCreate):
    try:
        channel = ChannelSchema(**payload.model_dump())
        new_id = create_document("channel", channel)
        return {"id": new_id, "message": "Channel added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/channels/seed")
def seed_channels():
    try:
        if db is None:
            raise Exception("Database not available")
        if db["channel"].count_documents({}) > 0:
            return {"message": "Channels already seeded"}
        defaults = [
            {
                "name": "Lofi Beats FM",
                "description": "Chill lofi for focus",
                "stream_url": "https://streams.ilovemusic.de/iloveradio9.mp3",
                "genre": "lofi",
            },
            {
                "name": "Classic Rock FM",
                "description": "Rock anthems 24/7",
                "stream_url": "https://stream.revma.ihrhls.com/zc1469",  # example
                "genre": "rock",
            },
            {
                "name": "Jazz Lounge",
                "description": "Smooth jazz and lounge",
                "stream_url": "https://us4.internet-radio.com/proxy/club107?mp=/stream",
                "genre": "jazz",
            },
        ]
        for ch in defaults:
            create_document("channel", ChannelSchema(**ch))
        return {"message": "Seeded default channels"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- AI VOICE COMMANDS ----------
class VoiceCommand(BaseModel):
    transcript: str

@app.post("/api/ai/command")
def ai_command(cmd: VoiceCommand):
    """
    Very simple intent parser:
    - "find song ..." / "play song ..."
    - "play channel ..." / "open radio ..."
    Returns items to act upon on the client.
    """
    t = (cmd.transcript or "").lower().strip()
    if not t:
        return {"action": "none", "message": "I didn't catch that."}

    # Channel intent
    if any(k in t for k in ["play channel", "open channel", "play radio", "open radio", "fm"]):
        # find by genre or name keyword
        keyword = t.replace("play", "").replace("open", "").replace("channel", "").replace("radio", "").replace("fm", "").strip()
        f: Dict[str, Any] = {}
        if keyword:
            f = {"$or": [
                {"name": {"$regex": keyword, "$options": "i"}},
                {"genre": {"$regex": keyword, "$options": "i"}},
            ]}
        items = get_documents("channel", f, 5)
        for d in items:
            if "_id" in d:
                d["id"] = str(d["_id"])
                del d["_id"]
        return {"action": "play_channel", "items": items, "message": f"Found {len(items)} channel(s)"}

    # Song intent
    if any(k in t for k in ["play song", "find song", "play", "find", "search"]):
        # extract possible title/artist after keywords
        keywords = t
        for k in ["play song", "find song", "search song", "search", "play"]:
            keywords = keywords.replace(k, "")
        query = keywords.strip()
        f: Dict[str, Any] = {}
        if query:
            f = {"$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"artist": {"$regex": query, "$options": "i"}},
            ]}
        items = get_documents("song", f, 10)
        for d in items:
            if "_id" in d:
                d["id"] = str(d["_id"])
                del d["_id"]
        return {"action": "play_song", "items": items, "message": f"Found {len(items)} song(s)"}

    return {"action": "none", "message": "Try: 'Play channel jazz' or 'Find song by Coldplay'"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
