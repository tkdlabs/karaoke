"use client";

import { useState } from "react";
import type { Song } from "@/types/karaoke";
import type { BulkStatus } from "@/lib/api";
import { SongPlayer } from "./SongPlayer";
import { LyricsEditor } from "./LyricsEditor";

function formatDuration(seconds: number | null): string {
  if (!seconds) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const STATUS_STYLES: Record<string, { label: string; color: string }> = {
  pending: { label: "Pending", color: "text-gray-400" },
  downloading: { label: "Downloading...", color: "text-yellow-400" },
  ready: { label: "Ready", color: "text-green-400" },
  error: { label: "Error", color: "text-red-400" },
};

function lyricsLabel(song: Song): { text: string; color: string } {
  if (song.lyrics_synced) return { text: "Synced", color: "text-green-400" };
  if (song.lyrics_plain) return { text: "Plain", color: "text-yellow-400" };
  return { text: "No lyrics", color: "text-gray-500" };
}

function stemsLabel(song: Song): { text: string; color: string } {
  switch (song.stems_status) {
    case "processing":
      return { text: "Separating...", color: "text-yellow-400" };
    case "ready":
      return { text: "Stems ready", color: "text-green-400" };
    case "error":
      return { text: "Stems error", color: "text-red-400" };
    default:
      return { text: "No stems", color: "text-gray-500" };
  }
}

function formatProgress(progress: number | null): string {
  if (progress == null || progress <= 0) return "";
  return ` ${Math.round(progress * 100)}%`;
}

function exportLabel(song: Song): { text: string; color: string } {
  switch (song.export_status) {
    case "processing": {
      const pct = formatProgress(song.export_progress);
      return { text: `Exporting${pct}...`, color: "text-yellow-400" };
    }
    case "ready": {
      const pct = song.export_vocal_level != null ? Math.round(song.export_vocal_level * 100) : 0;
      return { text: `Export (${pct}% vocals)`, color: "text-green-400" };
    }
    case "error":
      return { text: "Export error", color: "text-red-400" };
    default:
      return { text: "", color: "" };
  }
}

function overlayLabel(song: Song): { text: string; color: string } {
  switch (song.overlay_status) {
    case "processing": {
      const pct = formatProgress(song.overlay_progress);
      return { text: `Rendering${pct}...`, color: "text-yellow-400" };
    }
    case "ready":
      return { text: "Overlay ready", color: "text-green-400" };
    case "error":
      return { text: "Overlay error", color: "text-red-400" };
    default:
      return { text: "", color: "" };
  }
}

function variantsLabel(song: Song): { text: string; color: string } {
  switch (song.variants_status) {
    case "processing": {
      const pct = formatProgress(song.variants_progress);
      return { text: `Generating${pct}...`, color: "text-yellow-400" };
    }
    case "ready":
      return { text: "Playable", color: "text-green-400" };
    case "error":
      return { text: "Variants error", color: "text-red-400" };
    default:
      return { text: "", color: "" };
  }
}

interface SongLibraryProps {
  songs: Song[];
  onDelete: (id: string) => void;
  onLyricsSearch: (song: Song) => void;
  onLyricsDelete: (songId: string) => void;
  onStartStems: (songId: string, opts: { eq_match: boolean; exciter: boolean }) => void;
  onDeleteStems: (songId: string) => void;
  onStartExport: (songId: string, vocalLevel: number) => void;
  onDeleteExport: (songId: string) => void;
  getExportDownloadUrl: (songId: string) => string;
  onStartOverlay: (songId: string) => void;
  onDeleteOverlay: (songId: string) => void;
  getOverlayDownloadUrl: (songId: string) => string;
  onStartVariants: (songId: string, opts: { eq_match: boolean; exciter: boolean }) => void;
  onDeleteVariants: (songId: string) => void;
  onRegenerateThumbnail: (songId: string) => void;
  getVideoUrl: (songId: string, variant: "original" | "overlay_lyrics" | "overlay_romanized") => string;
  getThumbnailUrl: (songId: string) => string;
  deletingIds: Set<string>;
  onSongsRefresh: () => void;
  bulkStatus: BulkStatus | null;
  onStartBulkStems: (opts: { eq_match: boolean; exciter: boolean }) => void;
  onStartBulkVariants: (opts: { eq_match: boolean; exciter: boolean }) => void;
  onCancelBulk: () => void;
}

export function SongLibrary({
  songs,
  onDelete,
  onLyricsSearch,
  onLyricsDelete,
  onStartStems,
  onDeleteStems,
  onStartExport,
  onDeleteExport,
  getExportDownloadUrl,
  onStartOverlay,
  onDeleteOverlay,
  getOverlayDownloadUrl,
  onStartVariants,
  onDeleteVariants,
  onRegenerateThumbnail,
  getVideoUrl,
  getThumbnailUrl,
  deletingIds,
  onSongsRefresh,
  bulkStatus,
  onStartBulkStems,
  onStartBulkVariants,
  onCancelBulk,
}: SongLibraryProps) {
  const [vocalLevels, setVocalLevels] = useState<Record<string, number>>({});
  const [playingSong, setPlayingSong] = useState<{ song: Song; videoVariant: "original" | "overlay_lyrics" | "overlay_romanized" } | null>(null);
  const [editingLyricsSong, setEditingLyricsSong] = useState<Song | null>(null);
  const [eqMatchFlags, setEqMatchFlags] = useState<Record<string, boolean>>({});
  const [exciterFlags, setExciterFlags] = useState<Record<string, boolean>>({});
  const [bulkEqMatch, setBulkEqMatch] = useState(false);
  const [bulkExciter, setBulkExciter] = useState(false);

  if (songs.length === 0) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-3">Library</h2>
        <p className="text-gray-500">
          No songs yet. Search and add videos above.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-3">
        Library ({songs.length})
      </h2>
      {/* Bulk Operations */}
      <div className="mb-4 rounded-lg bg-gray-800 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-gray-300">Bulk</span>
          <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={bulkEqMatch}
              onChange={(e) => setBulkEqMatch(e.target.checked)}
              className="accent-teal-500"
              disabled={bulkStatus?.active ?? false}
            />
            EQ match
          </label>
          <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={bulkExciter}
              onChange={(e) => setBulkExciter(e.target.checked)}
              className="accent-sky-500"
              disabled={bulkStatus?.active ?? false}
            />
            Exciter
          </label>
          <button
            onClick={() => onStartBulkStems({ eq_match: bulkEqMatch, exciter: bulkExciter })}
            disabled={bulkStatus?.active ?? false}
            className="px-3 py-1 text-xs rounded bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
          >
            Regen All Stems
          </button>
          <button
            onClick={() => onStartBulkVariants({ eq_match: bulkEqMatch, exciter: bulkExciter })}
            disabled={bulkStatus?.active ?? false}
            className="px-3 py-1 text-xs rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
          >
            Regen All Variants
          </button>
          {bulkStatus?.active && (
            <button
              onClick={onCancelBulk}
              className="px-3 py-1 text-xs rounded bg-red-600 hover:bg-red-500 text-white"
            >
              Cancel
            </button>
          )}
        </div>
        {bulkStatus?.active && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>
                {bulkStatus.operation_type === "stems" ? "Stems" : "Variants"}{" "}
                {bulkStatus.completed}/{bulkStatus.total}
                {bulkStatus.current_song_title && (
                  <> — <span className="text-gray-300">{bulkStatus.current_song_title}</span></>
                )}
              </span>
              {bulkStatus.failed > 0 && (
                <span className="text-red-400">{bulkStatus.failed} failed</span>
              )}
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div
                className="bg-purple-500 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${bulkStatus.total > 0 ? (bulkStatus.completed / bulkStatus.total) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        )}
        {bulkStatus && !bulkStatus.active && bulkStatus.status === "completed" && bulkStatus.total > 0 && (
          <div className="mt-2 text-xs text-green-400">
            Completed: {bulkStatus.completed}/{bulkStatus.total}
            {bulkStatus.failed > 0 && (
              <span className="text-red-400 ml-2">{bulkStatus.failed} failed</span>
            )}
          </div>
        )}
        {bulkStatus && !bulkStatus.active && bulkStatus.status === "cancelled" && (
          <div className="mt-2 text-xs text-yellow-400">
            Cancelled: {bulkStatus.completed}/{bulkStatus.total} completed
          </div>
        )}
      </div>
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {songs.map((song) => {
          const status = STATUS_STYLES[song.status] || STATUS_STYLES.pending;
          const isDeleting = deletingIds.has(song.id);
          const lyrics = lyricsLabel(song);
          const stems = stemsLabel(song);
          const exp = exportLabel(song);
          const ovl = overlayLabel(song);
          const vars = variantsLabel(song);
          const hasLyrics = !!(song.lyrics_synced || song.lyrics_plain);
          const hasSyncedLyrics = !!song.lyrics_synced;
          const isReady = song.status === "ready";
          const canExport = song.stems_status === "ready";
          const canOverlay = isReady && hasSyncedLyrics;
          const canPlay = song.variants_status === "ready";
          const vocalLevel = vocalLevels[song.id] ?? 0.3;

          return (
            <div
              key={song.id}
              className="border border-gray-700 rounded-lg overflow-hidden"
            >
              {(song.status === "ready" || song.thumbnail_url) && (
                <div className="relative group">
                  <img
                    src={song.status === "ready" ? getThumbnailUrl(song.id) : song.thumbnail_url!}
                    alt={song.title}
                    className="w-full h-40 object-cover"
                  />
                  {isReady && (
                    <button
                      onClick={() => onRegenerateThumbnail(song.id)}
                      className="absolute top-1 right-1 px-1.5 py-0.5 text-xs bg-black/60 hover:bg-black/80 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Regenerate thumbnail"
                    >
                      Regen
                    </button>
                  )}
                </div>
              )}
              <div className="p-3">
                <a
                  href={song.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-sm line-clamp-2 hover:text-blue-400 transition-colors"
                >
                  {song.title}
                </a>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-gray-400 text-xs truncate">{song.artist}</span>
                  <span className="text-gray-600 text-xs">·</span>
                  <span className="text-gray-500 text-xs shrink-0">{formatDuration(song.duration)}</span>
                </div>

                {/* Status row */}
                <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 mt-2">
                  <span className={`text-xs ${status.color}`}>
                    {status.label}
                  </span>
                  <span className={`text-xs ${lyrics.color}`}>
                    {lyrics.text}
                  </span>
                  <span className={`text-xs ${stems.color}`}>
                    {stems.text}
                  </span>
                  {exp.text && (
                    <span className={`text-xs ${exp.color}`}>
                      {exp.text}
                    </span>
                  )}
                  {ovl.text && (
                    <span className={`text-xs ${ovl.color}`}>
                      {ovl.text}
                    </span>
                  )}
                  {vars.text && (
                    <span className={`text-xs ${vars.color}`}>
                      {vars.text}
                    </span>
                  )}
                </div>

                {/* Actions row */}
                <div className="flex items-center flex-wrap gap-1.5 mt-2">
                  <button
                    onClick={() => onLyricsSearch(song)}
                    disabled={!isReady}
                    className="px-2 py-1 text-xs bg-purple-900 hover:bg-purple-800 rounded disabled:opacity-40"
                  >
                    {hasLyrics ? "Re-search Lyrics" : "Search Lyrics"}
                  </button>
                  {hasSyncedLyrics && isReady && (
                    <button
                      onClick={() => setEditingLyricsSong(song)}
                      className="px-2 py-1 text-xs bg-violet-900 hover:bg-violet-800 rounded"
                    >
                      Edit Lyrics
                    </button>
                  )}
                  {hasLyrics && (
                    <button
                      onClick={() => onLyricsDelete(song.id)}
                      className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded"
                    >
                      Clear Lyrics
                    </button>
                  )}
                  {song.stems_status !== "ready" && (
                    <>
                      <button
                        onClick={() => onStartStems(song.id, { eq_match: eqMatchFlags[song.id] ?? false, exciter: exciterFlags[song.id] ?? false })}
                        disabled={!isReady || song.stems_status === "processing"}
                        className="px-2 py-1 text-xs bg-teal-900 hover:bg-teal-800 rounded disabled:opacity-40"
                      >
                        {song.stems_status === "processing"
                          ? "Separating..."
                          : song.stems_status === "error"
                            ? "Retry Separate"
                            : "Separate"}
                      </button>
                      {song.stems_status !== "processing" && isReady && (
                        <>
                          <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={eqMatchFlags[song.id] ?? false}
                              onChange={(e) =>
                                setEqMatchFlags((f) => ({ ...f, [song.id]: e.target.checked }))
                              }
                              className="accent-teal-500"
                            />
                            EQ match
                          </label>
                          <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={exciterFlags[song.id] ?? false}
                              onChange={(e) =>
                                setExciterFlags((f) => ({ ...f, [song.id]: e.target.checked }))
                              }
                              className="accent-teal-500"
                            />
                            Exciter
                          </label>
                        </>
                      )}
                    </>
                  )}
                  {song.stems_status === "ready" && (
                    <button
                      onClick={() => onDeleteStems(song.id)}
                      className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded"
                    >
                      Clear Stems
                    </button>
                  )}
                  <button
                    onClick={() => onDelete(song.id)}
                    disabled={isDeleting}
                    className="px-2 py-1 text-xs bg-red-900 hover:bg-red-800 rounded disabled:opacity-50 ml-auto"
                  >
                    {isDeleting ? "..." : "Delete"}
                  </button>
                </div>

                {/* Export row */}
                {canExport && (
                  <div className="flex flex-wrap items-center gap-2 mt-2 pt-2 border-t border-gray-700">
                    <div className="flex items-center gap-2 w-full min-w-0">
                      <label className="text-xs text-gray-400 shrink-0">
                        Vocals {Math.round(vocalLevel * 100)}%
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={Math.round(vocalLevel * 100)}
                        onChange={(e) =>
                          setVocalLevels((prev) => ({
                            ...prev,
                            [song.id]: Number(e.target.value) / 100,
                          }))
                        }
                        className="flex-1 h-1 accent-orange-500 min-w-0"
                      />
                    </div>
                    <button
                      onClick={() => onStartExport(song.id, vocalLevel)}
                      disabled={song.export_status === "processing"}
                      className="px-2 py-1 text-xs bg-orange-900 hover:bg-orange-800 rounded disabled:opacity-40 shrink-0"
                    >
                      {song.export_status === "processing"
                        ? `Exporting${formatProgress(song.export_progress)}...`
                        : song.export_status === "error"
                          ? "Retry Export"
                          : song.export_status === "ready"
                            ? "Re-export"
                            : "Export"}
                    </button>
                    {song.export_status === "ready" && (
                      <>
                        <a
                          href={getExportDownloadUrl(song.id)}
                          className="px-2 py-1 text-xs bg-green-900 hover:bg-green-800 rounded shrink-0"
                          download
                        >
                          Download
                        </a>
                        <button
                          onClick={() => onDeleteExport(song.id)}
                          className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded shrink-0"
                        >
                          Clear
                        </button>
                      </>
                    )}
                  </div>
                )}

                {/* Overlay row */}
                {canOverlay && (
                  <div className="flex flex-wrap items-center gap-2 mt-2 pt-2 border-t border-gray-700">
                    <button
                      onClick={() => onStartOverlay(song.id)}
                      disabled={song.overlay_status === "processing"}
                      className="px-2 py-1 text-xs bg-indigo-900 hover:bg-indigo-800 rounded disabled:opacity-40 shrink-0"
                    >
                      {song.overlay_status === "processing"
                        ? `Rendering${formatProgress(song.overlay_progress)}...`
                        : song.overlay_status === "error"
                          ? "Retry Overlay"
                          : song.overlay_status === "ready"
                            ? "Re-render"
                            : "Render Overlay"}
                    </button>
                    {song.overlay_status === "ready" && (
                      <>
                        <a
                          href={getOverlayDownloadUrl(song.id)}
                          className="px-2 py-1 text-xs bg-green-900 hover:bg-green-800 rounded shrink-0"
                          download
                        >
                          Download
                        </a>
                        <button
                          onClick={() => onDeleteOverlay(song.id)}
                          className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded shrink-0"
                        >
                          Clear
                        </button>
                      </>
                    )}
                  </div>
                )}

                {/* Variants + Play row */}
                {canExport && (
                  <div className="flex flex-wrap items-center gap-2 mt-2 pt-2 border-t border-gray-700">
                    {song.variants_status !== "ready" && (
                      <button
                        onClick={() => onStartVariants(song.id, { eq_match: eqMatchFlags[song.id] ?? false, exciter: exciterFlags[song.id] ?? false })}
                        disabled={song.variants_status === "processing"}
                        className="px-2 py-1 text-xs bg-sky-900 hover:bg-sky-800 rounded disabled:opacity-40 shrink-0"
                      >
                        {song.variants_status === "processing"
                          ? `Generating${formatProgress(song.variants_progress)}...`
                          : song.variants_status === "error"
                            ? "Retry Generate"
                            : "Generate Variants"}
                      </button>
                    )}
                    {song.variants_status === "ready" && (
                      <>
                        {song.overlay_status === "ready" ? (
                          <>
                            <button
                              onClick={() =>
                                setPlayingSong({ song, videoVariant: "overlay_romanized" })
                              }
                              className="px-3 py-1 text-xs bg-green-700 hover:bg-green-600 rounded shrink-0"
                            >
                              Play (romanized)
                            </button>
                            <button
                              onClick={() =>
                                setPlayingSong({ song, videoVariant: "overlay_lyrics" })
                              }
                              className="px-2 py-1 text-xs bg-green-800 hover:bg-green-700 rounded shrink-0"
                            >
                              Play (lyrics)
                            </button>
                            <button
                              onClick={() =>
                                setPlayingSong({ song, videoVariant: "original" })
                              }
                              className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded shrink-0"
                            >
                              Play (no lyrics)
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() =>
                              setPlayingSong({ song, videoVariant: "original" })
                            }
                            className="px-3 py-1 text-xs bg-green-700 hover:bg-green-600 rounded shrink-0"
                          >
                            Play
                          </button>
                        )}
                        <button
                          onClick={() => onDeleteVariants(song.id)}
                          className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded shrink-0"
                        >
                          Clear Variants
                        </button>
                      </>
                    )}
                    {song.variants_status !== "processing" && (
                      <>
                        <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none shrink-0 ml-1">
                          <input
                            type="checkbox"
                            checked={eqMatchFlags[song.id] ?? false}
                            onChange={(e) =>
                              setEqMatchFlags((f) => ({ ...f, [song.id]: e.target.checked }))
                            }
                            className="accent-sky-500"
                          />
                          EQ match
                        </label>
                        <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none shrink-0 ml-1">
                          <input
                            type="checkbox"
                            checked={exciterFlags[song.id] ?? false}
                            onChange={(e) =>
                              setExciterFlags((f) => ({ ...f, [song.id]: e.target.checked }))
                            }
                            className="accent-sky-500"
                          />
                          Exciter
                        </label>
                      </>
                    )}
                  </div>
                )}

                {song.status === "error" && song.error_message && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-2">
                    {song.error_message}
                  </p>
                )}
                {song.stems_status === "error" && song.stems_error && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-2">
                    Stems: {song.stems_error}
                  </p>
                )}
                {song.export_status === "error" && song.export_error && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-2">
                    Export: {song.export_error}
                  </p>
                )}
                {song.overlay_status === "error" && song.overlay_error && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-2">
                    Overlay: {song.overlay_error}
                  </p>
                )}
                {song.variants_status === "error" && song.variants_error && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-2">
                    Variants: {song.variants_error}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {playingSong && (
        <SongPlayer
          songId={playingSong.song.id}
          videoUrl={getVideoUrl(playingSong.song.id, playingSong.videoVariant)}
          duration={playingSong.song.duration || 0}
          title={playingSong.song.title}
          onClose={() => setPlayingSong(null)}
        />
      )}

      {editingLyricsSong && editingLyricsSong.lyrics_synced && (
        <LyricsEditor
          songId={editingLyricsSong.id}
          title={editingLyricsSong.title}
          duration={editingLyricsSong.duration || 0}
          lyricsSynced={editingLyricsSong.lyrics_synced}
          onClose={() => setEditingLyricsSong(null)}
          onSaved={onSongsRefresh}
        />
      )}
    </div>
  );
}
