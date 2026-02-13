"use client";

import { useState } from "react";
import { searchLyrics, setSongLyrics } from "@/lib/api";
import type { Song, LyricsSearchResult } from "@/types/karaoke";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function durationDiff(trackDur: number, songDur: number | null): string {
  if (!songDur) return "";
  const diff = trackDur - songDur;
  if (Math.abs(diff) < 1) return "exact match";
  return `${diff > 0 ? "+" : ""}${Math.round(diff)}s`;
}

const TYPE_BADGE: Record<string, { label: string; color: string }> = {
  synced: { label: "SYNCED", color: "bg-green-800 text-green-200" },
  plain: { label: "PLAIN", color: "bg-yellow-800 text-yellow-200" },
  instrumental: {
    label: "INSTRUMENTAL",
    color: "bg-gray-700 text-gray-300",
  },
  none: { label: "NO LYRICS", color: "bg-gray-700 text-gray-400" },
};

interface LyricsSearchModalProps {
  song: Song;
  onClose: () => void;
  onSaved: () => void;
}

export function LyricsSearchModal({
  song,
  onClose,
  onSaved,
}: LyricsSearchModalProps) {
  const defaultQuery = [song.artist, song.title]
    .filter(Boolean)
    .join(" ");

  const [query, setQuery] = useState(defaultQuery);
  const [results, setResults] = useState<LyricsSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError("");
    setResults([]);

    try {
      const data = await searchLyrics(query.trim(), song.duration ?? undefined);
      setResults(data);
      if (data.length === 0) setError("No results found.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelect = async (result: LyricsSearchResult) => {
    if (result.lyrics_type === "instrumental" || result.lyrics_type === "none")
      return;

    setSavingId(result.track_id);
    try {
      await setSongLyrics(song.id, {
        synced_lyrics: result.synced_lyrics,
        plain_lyrics: result.plain_lyrics,
        source: `lrclib:${result.track_id}`,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save lyrics");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-start justify-center z-50 pt-16 overflow-y-auto">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-2xl mx-4 mb-8">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div>
            <h2 className="font-semibold">Search Lyrics</h2>
            <p className="text-gray-400 text-sm mt-0.5">
              {song.title}
              {song.artist ? ` — ${song.artist}` : ""}
              {song.duration
                ? ` (${formatDuration(song.duration)})`
                : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white px-2 py-1"
          >
            Close
          </button>
        </div>

        {/* Search bar */}
        <form onSubmit={handleSearch} className="flex gap-2 p-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Artist and song name..."
            className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50"
          >
            {isSearching ? "..." : "Search"}
          </button>
        </form>

        {error && <p className="text-red-400 text-sm px-4 pb-2">{error}</p>}

        {/* Results */}
        {results.length > 0 && (
          <div className="px-4 pb-4 space-y-2 max-h-[60vh] overflow-y-auto">
            {results.map((r) => {
              const badge = TYPE_BADGE[r.lyrics_type] || TYPE_BADGE.none;
              const selectable =
                r.lyrics_type === "synced" || r.lyrics_type === "plain";
              const isSaving = savingId === r.track_id;

              return (
                <button
                  key={r.track_id}
                  onClick={() => handleSelect(r)}
                  disabled={!selectable || isSaving}
                  className={`w-full text-left border rounded-lg p-3 transition ${
                    selectable
                      ? "border-gray-600 hover:border-blue-500 cursor-pointer"
                      : "border-gray-800 opacity-50 cursor-not-allowed"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">
                        {r.artist_name} — {r.track_name}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {r.album_name} &middot;{" "}
                        {formatDuration(r.duration)}
                        {song.duration ? (
                          <span className="text-gray-500 ml-1">
                            ({durationDiff(r.duration, song.duration)})
                          </span>
                        ) : null}
                      </p>
                    </div>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded ${badge.color} ml-2 shrink-0`}
                    >
                      {badge.label}
                    </span>
                  </div>
                  {r.preview.length > 0 && (
                    <div className="mt-2 text-xs text-gray-500 font-mono space-y-0.5">
                      {r.preview.map((line, i) => (
                        <p key={i} className="truncate">
                          {line}
                        </p>
                      ))}
                    </div>
                  )}
                  {isSaving && (
                    <p className="text-blue-400 text-xs mt-1">Saving...</p>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
