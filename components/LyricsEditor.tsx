"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { getVideoUrl, adjustLyricsOffset } from "@/lib/api";

interface LrcLine {
  time: number; // seconds
  text: string;
}

function parseLrc(lrc: string): LrcLine[] {
  const lines: LrcLine[] = [];
  const re = /^\[(\d{2}):(\d{2})\.(\d{2})\]\s*(.*)$/;
  for (const raw of lrc.split("\n")) {
    const m = re.exec(raw.trim());
    if (m) {
      const time = parseInt(m[1]) * 60 + parseInt(m[2]) + parseInt(m[3]) / 100;
      lines.push({ time, text: m[4] });
    }
  }
  return lines;
}

function formatTimestamp(s: number): string {
  if (!s || !isFinite(s)) return "00:00:00.00";
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  const wholeSecs = Math.floor(secs);
  const centis = Math.floor((secs - wholeSecs) * 100);
  return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${wholeSecs.toString().padStart(2, "0")}.${centis.toString().padStart(2, "0")}`;
}

function formatLrcTime(s: number): string {
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  const wholeSecs = Math.floor(secs);
  const centis = Math.floor((secs - wholeSecs) * 100);
  return `${mins.toString().padStart(2, "0")}:${wholeSecs.toString().padStart(2, "0")}.${centis.toString().padStart(2, "0")}`;
}

interface LyricsEditorProps {
  songId: string;
  title: string;
  duration: number;
  lyricsSynced: string;
  onClose: () => void;
  onSaved: () => void;
}

export function LyricsEditor({
  songId,
  title,
  duration: totalDuration,
  lyricsSynced,
  onClose,
  onSaved,
}: LyricsEditorProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const lyricsContainerRef = useRef<HTMLDivElement>(null);
  const seekBarRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedLineIndex, setSelectedLineIndex] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [currentLyrics, setCurrentLyrics] = useState(lyricsSynced);

  const lrcLines = parseLrc(currentLyrics);

  // Find the current lyric line index
  const currentLineIndex = (() => {
    let idx = -1;
    for (let i = 0; i < lrcLines.length; i++) {
      if (lrcLines[i].time <= currentTime) idx = i;
      else break;
    }
    return idx;
  })();

  // Auto-scroll: prioritize selected line, fall back to current playback line
  const scrollTarget = selectedLineIndex ?? currentLineIndex;
  useEffect(() => {
    if (scrollTarget < 0 || !lyricsContainerRef.current) return;
    const container = lyricsContainerRef.current;
    const el = container.children[scrollTarget] as HTMLElement | undefined;
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [scrollTarget]);

  // Update currentTime from video
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeUpdate = () => setCurrentTime(video.currentTime);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);

    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, []);

  const handlePlayPause = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, []);

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const bar = seekBarRef.current;
      const video = videoRef.current;
      if (!bar || !video) return;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const newTime = ratio * totalDuration;
      video.currentTime = newTime;
      setCurrentTime(newTime);
    },
    [totalDuration]
  );

  const handleApply = useCallback(async () => {
    if (selectedLineIndex == null) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const updated = await adjustLyricsOffset(songId, currentTime, selectedLineIndex);
      if (updated.lyrics_synced) {
        setCurrentLyrics(updated.lyrics_synced);
      }
      setSaveMessage("Lyrics adjusted successfully!");
      setSelectedLineIndex(null);
      onSaved();
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to adjust lyrics"
      );
    } finally {
      setIsSaving(false);
    }
  }, [songId, currentTime, selectedLineIndex, onSaved]);

  const handleAnchorAndNext = useCallback(async () => {
    if (selectedLineIndex == null) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const updated = await adjustLyricsOffset(songId, currentTime, selectedLineIndex);
      if (updated.lyrics_synced) {
        setCurrentLyrics(updated.lyrics_synced);
      }
      const nextLines = parseLrc(updated.lyrics_synced || "");
      if (selectedLineIndex + 1 < nextLines.length) {
        setSelectedLineIndex(selectedLineIndex + 1);
      } else {
        setSelectedLineIndex(null);
        setSaveMessage("All lines anchored!");
      }
      onSaved();
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to adjust lyrics"
      );
    } finally {
      setIsSaving(false);
    }
  }, [songId, currentTime, selectedLineIndex, onSaved]);

  const handleLyricClick = useCallback((index: number) => {
    setSelectedLineIndex((prev) => (prev === index ? null : index));
    setSaveMessage(null);
  }, []);

  const handleLyricDoubleClick = useCallback((time: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = time;
    setCurrentTime(time);
  }, []);

  const progress = totalDuration > 0 ? (currentTime / totalDuration) * 100 : 0;

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-lg max-w-4xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700 shrink-0">
          <h3 className="text-sm font-medium truncate">Edit Lyrics — {title}</h3>
          <button
            onClick={() => {
              videoRef.current?.pause();
              onClose();
            }}
            className="text-gray-400 hover:text-white text-lg px-2"
          >
            X
          </button>
        </div>

        {/* Video */}
        <video
          ref={videoRef}
          src={getVideoUrl(songId, "original")}
          playsInline
          preload="auto"
          className="w-full aspect-video bg-black shrink-0"
          onClick={handlePlayPause}
        />

        {/* Transport controls */}
        <div className="px-4 py-2 space-y-2 shrink-0 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <button
              onClick={handlePlayPause}
              className="px-4 py-1.5 text-sm bg-blue-700 hover:bg-blue-600 rounded shrink-0"
            >
              {isPlaying ? "Pause" : "Play"}
            </button>
            <span className="text-sm font-mono text-gray-200">
              {formatTimestamp(currentTime)}
            </span>
            <span className="text-xs text-gray-500">/</span>
            <span className="text-sm font-mono text-gray-400">
              {formatTimestamp(totalDuration)}
            </span>
          </div>

          {/* Seek bar */}
          <div
            ref={seekBarRef}
            onClick={handleSeek}
            className="w-full h-2 bg-gray-700 rounded cursor-pointer relative"
          >
            <div
              className="h-full bg-blue-500 rounded"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Lyrics panel */}
        <div
          ref={lyricsContainerRef}
          className="flex-1 overflow-y-auto px-4 py-2 min-h-0"
        >
          {lrcLines.length === 0 ? (
            <p className="text-gray-500 text-sm">No synced lyrics to display.</p>
          ) : (
            lrcLines.map((line, i) => {
              const isSelected = i === selectedLineIndex;
              const isCurrent = i === currentLineIndex;
              return (
                <div
                  key={i}
                  onClick={() => handleLyricClick(i)}
                  onDoubleClick={() => handleLyricDoubleClick(line.time)}
                  className={`py-1 px-2 rounded cursor-pointer text-sm font-mono transition-colors ${
                    isSelected
                      ? "bg-orange-900/60 text-orange-200 ring-1 ring-orange-500"
                      : isCurrent
                        ? "bg-blue-900/50 text-blue-200"
                        : "text-gray-400 hover:bg-gray-800"
                  }`}
                >
                  <span className="text-gray-600 mr-2">
                    [{formatLrcTime(line.time)}]
                  </span>
                  {line.text || <span className="text-gray-700">♪</span>}
                </div>
              );
            })
          )}
        </div>

        {/* Offset controls */}
        <div className="px-4 py-3 border-t border-gray-700 shrink-0 space-y-2">
          <p className="text-xs text-gray-500">
            Click a line to select it, then Apply Offset to set it to the current video time. Double-click to seek.
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            {selectedLineIndex != null && lrcLines[selectedLineIndex] && (
              <>
                <span className="text-xs text-gray-400">Selected:</span>
                <span className="text-sm font-mono text-orange-300 truncate max-w-xs">
                  [{formatLrcTime(lrcLines[selectedLineIndex].time)}] {lrcLines[selectedLineIndex].text || "♪"}
                </span>
                <span className="text-xs text-gray-500">→</span>
                <span className="text-sm font-mono text-green-300">
                  {formatTimestamp(currentTime)}
                </span>
                <button
                  onClick={handleApply}
                  disabled={isSaving}
                  className="px-3 py-1.5 text-sm bg-green-700 hover:bg-green-600 rounded disabled:opacity-50 shrink-0"
                >
                  {isSaving ? "Applying..." : "Apply Offset"}
                </button>
                <button
                  onClick={handleAnchorAndNext}
                  disabled={isSaving}
                  className="px-3 py-1.5 text-sm bg-orange-700 hover:bg-orange-600 rounded disabled:opacity-50 shrink-0"
                >
                  {isSaving ? "..." : "Anchor & Next"}
                </button>
              </>
            )}
            {selectedLineIndex == null && (
              <span className="text-xs text-gray-500 italic">No line selected</span>
            )}
          </div>
          {saveMessage && (
            <p
              className={`text-xs ${
                saveMessage.includes("success")
                  ? "text-green-400"
                  : "text-red-400"
              }`}
            >
              {saveMessage}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
