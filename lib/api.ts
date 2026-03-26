import type {
  SearchResult,
  Song,
  AddSongRequest,
  LyricsSearchResult,
  SetLyricsRequest,
  AdjustLyricsRequest,
} from "@/types/karaoke";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8001`
    : "http://localhost:8001");

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

export interface AudioEnhanceOptions {
  eq_match: boolean;
  exciter: boolean;
  deep_clean?: boolean;
}

export async function startStems(songId: string, opts: AudioEnhanceOptions): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/stems`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
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

export async function startOverlay(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/overlay`, { method: "POST" });
}

export async function deleteOverlay(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/overlay`, { method: "DELETE" });
}

export function getOverlayDownloadUrl(songId: string): string {
  return `${API_BASE}/api/songs/${songId}/overlay/download`;
}

export function getAudioStemUrl(songId: string, stem: "vocals" | "instrumental"): string {
  return `${API_BASE}/api/songs/${songId}/audio/${stem}`;
}

export type VideoVariant = "original" | "overlay_lyrics" | "overlay_romanized";

export function getVideoUrl(songId: string, variant: VideoVariant): string {
  return `${API_BASE}/api/songs/${songId}/video/${variant}`;
}

export function getThumbnailUrl(songId: string): string {
  return `${API_BASE}/api/songs/${songId}/thumbnail`;
}

export async function regenerateThumbnail(songId: string): Promise<void> {
  await fetchApi(`/api/songs/${songId}/thumbnail`, { method: "POST" });
}

export function getVariantUrl(songId: string, pitch: number, vocal: number): string {
  return `${API_BASE}/api/songs/${songId}/variants/${pitch}/${vocal}`;
}

export async function startVariants(songId: string, opts: AudioEnhanceOptions): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/variants`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function deleteVariants(songId: string): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/variants`, { method: "DELETE" });
}

export async function adjustLyricsOffset(
  songId: string,
  anchorTime: number,
  anchorLineIndex: number
): Promise<Song> {
  return fetchApi(`/api/songs/${songId}/lyrics/adjust`, {
    method: "PUT",
    body: JSON.stringify({
      anchor_time: anchorTime,
      anchor_line_index: anchorLineIndex,
    } satisfies AdjustLyricsRequest),
  });
}

// ── Bulk operations ──────────────────────────────────────────────────────────

export interface BulkRequest {
  song_ids?: string[];
  eq_match: boolean;
  exciter: boolean;
  deep_clean: boolean;
  clear_existing: boolean;
}

export interface BulkOperationResponse {
  operation_id: string;
  operation_type: string;
  total: number;
  song_ids: string[];
}

export interface BulkStatus {
  active: boolean;
  operation_id: string | null;
  operation_type: string | null;
  status: string | null;
  total: number;
  completed: number;
  failed: number;
  current_song_id: string | null;
  current_song_title: string | null;
  queue: string[];
  errors: Record<string, string>;
}

export async function startBulkStems(req: BulkRequest): Promise<BulkOperationResponse> {
  return fetchApi("/api/bulk/stems", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function startBulkVariants(req: BulkRequest): Promise<BulkOperationResponse> {
  return fetchApi("/api/bulk/variants", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getBulkStatus(): Promise<BulkStatus> {
  return fetchApi("/api/bulk/status");
}

export async function cancelBulk(): Promise<void> {
  await fetchApi("/api/bulk/cancel", { method: "POST" });
}
