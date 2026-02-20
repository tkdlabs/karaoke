"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { getVariantUrl } from "@/lib/api";

const SYNC_TOLERANCE = 0.1; // max audio-video drift before resyncing
const CROSSFADE_MS = 1000; // crossfade duration when switching variants
const OFFSET_AHEAD = 3; // seconds ahead to start new variant on switch

const PITCHES = [-3, -2, -1, 0, 1, 2, 3] as const;
const VOCALS = [
  { value: 0, label: "Off" },
  { value: 25, label: "Guide" },
  { value: 100, label: "Full" },
] as const;

interface SongPlayerProps {
  songId: string;
  videoUrl: string;
  duration: number;
  title: string;
  onClose: () => void;
}

export function SongPlayer({
  songId,
  videoUrl,
  duration: totalDuration,
  title,
  onClose,
}: SongPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioARef = useRef<HTMLAudioElement>(null);
  const audioBRef = useRef<HTMLAudioElement>(null);
  // true = A is active, false = B is active
  const activeIsARef = useRef(true);
  const crossfadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [pitch, setPitch] = useState(0);
  const [vocal, setVocal] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);

  const getActiveAudio = useCallback(
    () => (activeIsARef.current ? audioARef.current : audioBRef.current),
    []
  );
  const getStandbyAudio = useCallback(
    () => (activeIsARef.current ? audioBRef.current : audioARef.current),
    []
  );

  /** Wait for an audio or video element to be ready to play */
  function waitForCanPlay(el: HTMLMediaElement): Promise<void> {
    return new Promise((resolve) => {
      if (el.readyState >= 3) {
        resolve();
      } else {
        const onReady = () => {
          el.removeEventListener("canplay", onReady);
          resolve();
        };
        el.addEventListener("canplay", onReady);
      }
    });
  }

  /** Start playback from the beginning or current position */
  const handlePlay = useCallback(async () => {
    const audio = getActiveAudio();
    const video = videoRef.current;
    if (!audio) return;

    const url = getVariantUrl(songId, pitch, vocal);
    audio.src = url;
    audio.currentTime = currentTime;
    audio.volume = 1;

    if (video) {
      video.currentTime = currentTime;
    }

    // Wait for both to be ready
    const waits: Promise<void>[] = [waitForCanPlay(audio)];
    if (video) waits.push(waitForCanPlay(video));
    await Promise.all(waits);

    audio.play().catch((err) => console.warn("Audio play failed:", err));
    video?.play().catch((err) => console.warn("Video play failed:", err));
    setIsPlaying(true);
  }, [songId, pitch, vocal, currentTime, getActiveAudio]);

  const handlePause = useCallback(() => {
    const audio = getActiveAudio();
    if (audio) {
      setCurrentTime(audio.currentTime);
      audio.pause();
    }
    videoRef.current?.pause();
    setIsPlaying(false);
  }, [getActiveAudio]);

  /** Switch to a different variant with crossfade */
  const switchVariant = useCallback(
    async (newPitch: number, newVocal: number) => {
      const active = getActiveAudio();
      const standby = getStandbyAudio();
      if (!active || !standby || !isPlaying) return;

      // Cancel any in-progress crossfade
      if (crossfadeTimerRef.current) {
        clearTimeout(crossfadeTimerRef.current);
        crossfadeTimerRef.current = null;
      }

      const switchTime = active.currentTime + OFFSET_AHEAD;
      const url = getVariantUrl(songId, newPitch, newVocal);

      standby.src = url;
      standby.currentTime = switchTime;
      standby.volume = 0;

      await waitForCanPlay(standby);

      // Schedule the crossfade to happen when active reaches switchTime
      const delay = Math.max(0, (switchTime - active.currentTime) * 1000);

      crossfadeTimerRef.current = setTimeout(() => {
        standby.play().catch(() => {});

        // Animate crossfade
        const steps = 20;
        const stepMs = CROSSFADE_MS / steps;
        let step = 0;
        const interval = setInterval(() => {
          step++;
          const t = step / steps;
          standby.volume = t;
          active.volume = 1 - t;
          if (step >= steps) {
            clearInterval(interval);
            active.pause();
            active.removeAttribute("src");
            activeIsARef.current = !activeIsARef.current;
          }
        }, stepMs);
      }, delay);
    },
    [songId, isPlaying, getActiveAudio, getStandbyAudio]
  );

  // Handle pitch/vocal changes
  const handlePitchChange = useCallback(
    (newPitch: number) => {
      setPitch(newPitch);
      if (isPlaying) {
        switchVariant(newPitch, vocal);
      }
    },
    [isPlaying, vocal, switchVariant]
  );

  const handleVocalChange = useCallback(
    (newVocal: number) => {
      setVocal(newVocal);
      if (isPlaying) {
        switchVariant(pitch, newVocal);
      }
    },
    [isPlaying, pitch, switchVariant]
  );

  // Polling loop: sync video to audio + update time display
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      const audio = activeIsARef.current
        ? audioARef.current
        : audioBRef.current;
      const video = videoRef.current;
      if (!audio) return;

      const t = audio.currentTime;
      setCurrentTime(t);

      if (video && Math.abs(video.currentTime - t) > SYNC_TOLERANCE) {
        video.currentTime = t;
      }

      if (t >= totalDuration) {
        handlePause();
      }
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying, totalDuration, handlePause]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (crossfadeTimerRef.current) clearTimeout(crossfadeTimerRef.current);
      audioARef.current?.pause();
      audioBRef.current?.pause();
    };
  }, []);

  function formatTime(s: number): string {
    if (!s || !isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-lg max-w-3xl w-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
          <h3 className="text-sm font-medium truncate">{title}</h3>
          <button
            onClick={() => {
              handlePause();
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
          src={videoUrl}
          muted
          playsInline
          preload="auto"
          className="w-full aspect-video bg-black"
          onClick={() => (isPlaying ? handlePause() : handlePlay())}
        />

        {/* Hidden audio elements for A/B crossfade */}
        <audio ref={audioARef} preload="auto" />
        <audio ref={audioBRef} preload="auto" />

        {/* Controls */}
        <div className="px-4 py-3 space-y-3">
          {/* Play + time */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => (isPlaying ? handlePause() : handlePlay())}
              className="px-4 py-1.5 text-sm bg-blue-700 hover:bg-blue-600 rounded shrink-0"
            >
              {isPlaying ? "Pause" : "Play"}
            </button>
            <span className="text-xs text-gray-400">
              {formatTime(currentTime)} / {formatTime(totalDuration)}
            </span>
          </div>

          {/* Pitch selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 shrink-0 w-14">Pitch</span>
            <div className="flex gap-1">
              {PITCHES.map((p) => (
                <button
                  key={p}
                  onClick={() => handlePitchChange(p)}
                  className={`px-2 py-1 text-xs rounded ${
                    pitch === p
                      ? "bg-violet-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  {p > 0 ? `+${p}` : p}
                </button>
              ))}
            </div>
          </div>

          {/* Vocal selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 shrink-0 w-14">Vocals</span>
            <div className="flex gap-1">
              {VOCALS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => handleVocalChange(value)}
                  className={`px-3 py-1 text-xs rounded ${
                    vocal === value
                      ? "bg-orange-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
