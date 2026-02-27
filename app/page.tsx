"use client";

import { useState, useEffect, useCallback } from "react";
import { searchVideos, listSongs, addSong, deleteSong, deleteSongLyrics, startStems, deleteStems, startExport, deleteExport, getExportDownloadUrl, startOverlay, deleteOverlay, getOverlayDownloadUrl, startVariants, deleteVariants, getVideoUrl, getThumbnailUrl, regenerateThumbnail } from "@/lib/api";
import { SearchResults } from "@/components/SearchResults";
import { SongLibrary } from "@/components/SongLibrary";
import { LyricsSearchModal } from "@/components/LyricsSearchModal";
import type { SearchResult, Song } from "@/types/karaoke";

export default function Home() {
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [songs, setSongs] = useState<Song[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [addingSongs, setAddingSongs] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [lyricsSearchSong, setLyricsSearchSong] = useState<Song | null>(null);

  const loadSongs = useCallback(async () => {
    try {
      const data = await listSongs();
      setSongs(data);
    } catch {
      // Silently fail — library will appear empty
    }
  }, []);

  // Load library on mount and poll for status updates
  useEffect(() => {
    loadSongs();
    const interval = setInterval(loadSongs, 3000);
    return () => clearInterval(interval);
  }, [loadSongs]);

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

  const handleLyricsDelete = async (songId: string) => {
    try {
      await deleteSongLyrics(songId);
      await loadSongs();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to clear lyrics");
    }
  };

  const handleStartStems = async (songId: string, opts: { eq_match: boolean; exciter: boolean }) => {
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

      {searchError && (
        <p className="text-red-400 text-sm">{searchError}</p>
      )}

      {/* Search Results */}
      <SearchResults
        results={searchResults}
        addingSongs={addingSongs}
        onAdd={handleAdd}
      />

      {/* Song Library */}
      <SongLibrary
        songs={songs}
        onDelete={handleDelete}
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
        onSongsRefresh={loadSongs}
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
