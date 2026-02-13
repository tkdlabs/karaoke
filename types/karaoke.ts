export interface SearchResult {
  video_id: string;
  title: string;
  artist: string;
  duration: number;
  thumbnail_url: string;
  url: string;
}

export interface Song {
  id: string;
  title: string;
  artist: string | null;
  duration: number | null;
  source_url: string;
  video_filename: string | null;
  thumbnail_url: string | null;
  status: "pending" | "downloading" | "ready" | "error";
  error_message: string | null;
  lyrics_synced: string | null;
  lyrics_plain: string | null;
  lyrics_source: string | null;
  vocals_filename: string | null;
  instrumental_filename: string | null;
  stems_status: "processing" | "ready" | "error" | null;
  stems_error: string | null;
  export_filename: string | null;
  export_status: "processing" | "ready" | "error" | null;
  export_error: string | null;
  export_vocal_level: number | null;
  created_at: string;
  updated_at: string;
}

export interface AddSongRequest {
  url: string;
  title: string;
  artist: string;
  duration: number;
  thumbnail_url: string;
}

export interface LyricsSearchResult {
  track_id: number;
  track_name: string;
  artist_name: string;
  album_name: string;
  duration: number;
  lyrics_type: "synced" | "plain" | "instrumental" | "none";
  synced_lyrics: string | null;
  plain_lyrics: string | null;
  preview: string[];
}

export interface SetLyricsRequest {
  synced_lyrics: string | null;
  plain_lyrics: string | null;
  source: string;
}
