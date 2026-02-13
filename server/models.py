"""Pydantic models for the karaoke API."""

from pydantic import BaseModel


class SearchResult(BaseModel):
    video_id: str
    title: str
    artist: str
    duration: float
    thumbnail_url: str
    url: str


class AddSongRequest(BaseModel):
    url: str
    title: str
    artist: str
    duration: float
    thumbnail_url: str


class Song(BaseModel):
    id: str
    title: str
    artist: str | None = None
    duration: float | None = None
    source_url: str
    video_filename: str | None = None
    thumbnail_url: str | None = None
    status: str = "pending"
    error_message: str | None = None
    lyrics_synced: str | None = None
    lyrics_plain: str | None = None
    lyrics_source: str | None = None
    vocals_filename: str | None = None
    instrumental_filename: str | None = None
    stems_status: str | None = None  # None | "processing" | "ready" | "error"
    stems_error: str | None = None
    export_filename: str | None = None
    export_status: str | None = None  # None | "processing" | "ready" | "error"
    export_error: str | None = None
    export_vocal_level: float | None = None
    created_at: str
    updated_at: str


class LyricsSearchResult(BaseModel):
    track_id: int
    track_name: str
    artist_name: str
    album_name: str
    duration: float
    lyrics_type: str  # "synced" | "plain" | "instrumental" | "none"
    synced_lyrics: str | None = None
    plain_lyrics: str | None = None
    preview: list[str] = []


class SetLyricsRequest(BaseModel):
    synced_lyrics: str | None = None
    plain_lyrics: str | None = None
    source: str  # e.g. "lrclib:12345" or "manual"


class ExportRequest(BaseModel):
    vocal_level: float = 0.3  # 0.0 = pure instrumental, 1.0 = full vocals
