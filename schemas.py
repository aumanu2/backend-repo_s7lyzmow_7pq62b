"""
Database Schemas for the Spotify-like app

Each Pydantic model represents a collection in your MongoDB database.
Collection name is the lowercase of the class name.

- Song -> "song"
- Playlist -> "playlist"
- Channel -> "channel"
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class Song(BaseModel):
    """
    Songs collection schema
    """
    title: str = Field(..., description="Song title")
    artist: str = Field(..., description="Artist name")
    album: Optional[str] = Field(None, description="Album name")
    cover_url: Optional[str] = Field(None, description="Cover image URL")
    audio_url: Optional[str] = Field(None, description="Public URL of uploaded audio file")
    duration_sec: Optional[int] = Field(None, ge=0, description="Duration in seconds")
    genre: Optional[str] = Field(None, description="Music genre")

class Playlist(BaseModel):
    """
    Playlists collection schema
    """
    name: str = Field(..., description="Playlist name")
    description: Optional[str] = Field(None, description="Short description")
    song_ids: List[str] = Field(default_factory=list, description="List of Song document IDs")

class Channel(BaseModel):
    """
    FM/Radio channels collection schema
    """
    name: str = Field(..., description="Channel name")
    description: Optional[str] = Field(None, description="What this channel plays")
    stream_url: str = Field(..., description="Streaming URL (mp3/aac/m3u8)")
    genre: Optional[str] = Field(None, description="Channel genre")
