"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { searchVideos, listSongs, addSong, importVideo, getCapabilities, deleteSong, deleteSongLyrics, startStems, deleteStems, startExport, deleteExport, getExportDownloadUrl, startOverlay, deleteOverlay, getOverlayDownloadUrl, startVariants, deleteVariants, getVideoUrl, getThumbnailUrl, regenerateThumbnail, startBulkStems, startBulkVariants, getBulkStatus, cancelBulk } from "@/lib/api";
import type { BulkStatus } from "@/lib/api";
import { SearchResults } from "@/components/SearchResults";
import { SongLibrary } from "@/components/SongLibrary";
import { LyricsSearchModal } from "@/components/LyricsSearchModal";
import type { SearchResult, Song } from "@/types/karaoke";

const POLL_ACTIVE_MS = 3000;   // any song is downloading / processing
const POLL_IDLE_MS = 20000;    // all songs are at rest

function hasActiveProcessing(songs: Song[]): boolean {
  return songs.some(
    (s) =>
      s.status === "downloading" ||
      s.status === "pending" ||
      s.stems_status === "processing" ||
      s.variants_status === "processing" ||
      s.overlay_status === "processing" ||
      s.export_status === "processing",
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [songs, setSongs] = useState<Song[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [addingSongs, setAddingSongs] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [lyricsSearchSong, setLyricsSearchSong] = useState<Song | null>(null);
  const [bulkStatus, setBulkStatus] = useState<BulkStatus | null>(null);
  const [ytdlpAvailable, setYtdlpAvailable] = useState<boolean | null>(null);
  const [stemsModel, setStemsModel] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSongs = useCallback(async () => {
    try {
      const data = await listSongs();
      setSongs(data);
      getBulkStatus().then(setBulkStatus).catch(() => {});
      // Schedule next poll: fast when something is actively processing, slow otherwise
      const delay = hasActiveProcessing(data) ? POLL_ACTIVE_MS : POLL_IDLE_MS;
      timerRef.current = setTimeout(loadSongs, delay);
    } catch {
      // Silently fail — retry at the slow cadence
      timerRef.current = setTimeout(loadSongs, POLL_IDLE_MS);
    }
  }, []);

  // Load library on mount; polling is self-scheduling via setTimeout above
  useEffect(() => {
    loadSongs();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [loadSongs]);

  // Detect runtime capabilities (yt-dlp optional) so search UI can hide
  useEffect(() => {
    getCapabilities()
      .then((c) => {
        setYtdlpAvailable(c.ytdlp);
        setStemsModel(c.stems_model);
      })
      .catch(() => setYtdlpAvailable(null));
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setSearchError("");
    setSearchResults([]);

    try {
      const results = await searchVideos(query.trim());
      setSearchResults(results);
    } catch (err) {
      setSearchError(
        err instanceof Error ? err.message : "Search failed"
      );
    } finally {
      setIsSearching(false);
    }
  };

  const handleAdd = async (result: SearchResult) => {
    setAddingSongs((prev) => new Set(prev).add(result.video_id));
    try {
      await addSong({
        url: result.url,
        title: result.title,
        artist: result.artist,
        duration: result.duration,
        thumbnail_url: result.thumbnail_url,
      });
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add song");
    } finally {
      setAddingSongs((prev) => {
        const next = new Set(prev);
        next.delete(result.video_id);
        return next;
      });
    }
  };

  const handleImport = async (file: File) => {
    await importVideo(file);
    await loadSongs();
  };

  const handleLyricsDelete = async (songId: string) => {
    try {
      await deleteSongLyrics(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear lyrics");
    }
  };

  const handleStartStems = async (songId: string, opts: { eq_match: boolean; exciter: boolean; passes: number }) => {
    try {
      await startStems(songId, opts);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start separation");
    }
  };

  const handleDeleteStems = async (songId: string) => {
    try {
      await deleteStems(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear stems");
    }
  };

  const handleStartExport = async (songId: string, vocalLevel: number) => {
    try {
      await startExport(songId, vocalLevel);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start export");
    }
  };

  const handleDeleteExport = async (songId: string) => {
    try {
      await deleteExport(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear export");
    }
  };

  const handleStartOverlay = async (songId: string) => {
    try {
      await startOverlay(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start overlay");
    }
  };

  const handleDeleteOverlay = async (songId: string) => {
    try {
      await deleteOverlay(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear overlay");
    }
  };

  const handleStartVariants = async (songId: string, opts: { eq_match: boolean; exciter: boolean }) => {
    try {
      await startVariants(songId, opts);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start variant generation");
    }
  };

  const handleDeleteVariants = async (songId: string) => {
    try {
      await deleteVariants(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear variants");
    }
  };

  const handleRegenerateThumbnail = async (songId: string) => {
    try {
      await regenerateThumbnail(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to regenerate thumbnail");
    }
  };

  const handleStartBulkStems = async (opts: { eq_match: boolean; exciter: boolean; passes: number; clear_existing: boolean }) => {
    try {
      await startBulkStems(opts);
      const status = await getBulkStatus();
      setBulkStatus(status);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start bulk stems");
    }
  };

  const handleStartBulkVariants = async (opts: { eq_match: boolean; exciter: boolean; passes: number; clear_existing: boolean }) => {
    try {
      await startBulkVariants(opts);
      const status = await getBulkStatus();
      setBulkStatus(status);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start bulk variants");
    }
  };

  const handleCancelBulk = async () => {
    try {
      await cancelBulk();
      const status = await getBulkStatus();
      setBulkStatus(status);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to cancel bulk operation");
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingIds((prev) => new Set(prev).add(id));
    try {
      await deleteSong(id);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete song");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  return (
    <div className="space-y-8">
      {/* Search */}
      {ytdlpAvailable !== false && (
        <form onSubmit={handleSearch} className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for a song or music video..."
            className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
          >
            {isSearching ? "Searching..." : "Search"}
          </button>
        </form>
      )}

      {ytdlpAvailable === false && (
        <p className="text-gray-400 text-sm">
          yt-dlp is not installed, so YouTube search is disabled. Use{" "}
          <span className="text-emerald-400">Import video</span> in the library to add your
          own files.
        </p>
      )}

      {searchError && (
        <p className="text-red-400 text-sm">{searchError}</p>
      )}

      {/* Search Results */}
      {ytdlpAvailable !== false && (
        <SearchResults
          results={searchResults}
          addingSongs={addingSongs}
          onAdd={handleAdd}
        />
      )}

      {/* Song Library */}
      <SongLibrary
        songs={songs}
        onDelete={handleDelete}
        onImport={handleImport}
        onLyricsSearch={(song) => setLyricsSearchSong(song)}
        onLyricsDelete={handleLyricsDelete}
        onStartStems={handleStartStems}
        onDeleteStems={handleDeleteStems}
        onStartExport={handleStartExport}
        onDeleteExport={handleDeleteExport}
        getExportDownloadUrl={getExportDownloadUrl}
        onStartOverlay={handleStartOverlay}
        onDeleteOverlay={handleDeleteOverlay}
        getOverlayDownloadUrl={getOverlayDownloadUrl}
        onStartVariants={handleStartVariants}
        onDeleteVariants={handleDeleteVariants}
        onRegenerateThumbnail={handleRegenerateThumbnail}
        getVideoUrl={getVideoUrl}
        getThumbnailUrl={getThumbnailUrl}
        deletingIds={deletingIds}
        stemsModel={stemsModel}
        onSongsRefresh={loadSongs}
        bulkStatus={bulkStatus}
        onStartBulkStems={handleStartBulkStems}
        onStartBulkVariants={handleStartBulkVariants}
        onCancelBulk={handleCancelBulk}
      />

      {/* Lyrics Search Modal */}
      {lyricsSearchSong && (
        <LyricsSearchModal
          song={lyricsSearchSong}
          onClose={() => setLyricsSearchSong(null)}
          onSaved={loadSongs}
        />
      )}
    </div>
  );
}
