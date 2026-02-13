import type {
  SearchResult,
  Song,
  AddSongRequest,
  LyricsSearchResult,
  SetLyricsRequest,
} from "@/types/karaoke";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function searchVideos(query: string): Promise<SearchResult[]> {
  return fetchApi(`/api/search?q=${encodeURIComponent(query)}`);
}

export async function listSongs(): Promise<Song[]> {
  return fetchApi("/api/songs");
}

export async function getSong(id: string): Promise<Song> {
  return fetchApi(`/api/songs/${id}`);
}

export async function addSong(req: AddSongRequest): Promise<Song> {
  return fetchApi("/api/songs", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function deleteSong(id: string): Promise<void> {
  await fetchApi(`/api/songs/${id}`, { method: "DELETE" });
}

export async function searchLyrics(
  query: string,
  duration?: number
): Promise<LyricsSearchResult[]> {
  let url = `/api/lyrics/search?q=${encodeURIComponent(query)}`;
  if (duration) url += `&duration=${duration}`;
  return fetchApi(url);
}

export async function setSongLyrics(
  songId: string,
  req: SetLyricsRequest
): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/lyrics`, {
    method: "PUT",
    body: JSON.stringify(req),
  });
}

export async function deleteSongLyrics(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/lyrics`, { method: "DELETE" });
}

export async function startStems(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/stems`, { method: "POST" });
}

export async function deleteStems(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/stems`, { method: "DELETE" });
}

export async function startExport(
  songId: string,
  vocalLevel: number
): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/export`, {
    method: "POST",
    body: JSON.stringify({ vocal_level: vocalLevel }),
  });
}

export async function deleteExport(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/export`, { method: "DELETE" });
}

export function getExportDownloadUrl(songId: string): string {
  return `${API_BASE}/api/songs/${songId}/export/download`;
}
