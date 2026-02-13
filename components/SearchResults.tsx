"use client";

import type { SearchResult } from "@/types/karaoke";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface SearchResultsProps {
  results: SearchResult[];
  addingSongs: Set<string>;
  onAdd: (result: SearchResult) => void;
}

export function SearchResults({
  results,
  addingSongs,
  onAdd,
}: SearchResultsProps) {
  if (results.length === 0) return null;

  return (
    <div>
      <h2 className="text-lg font-semibold mb-3">Search Results</h2>
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {results.map((r) => {
          const isAdding = addingSongs.has(r.video_id);
          return (
            <div
              key={r.video_id}
              className="border border-gray-700 rounded-lg overflow-hidden"
            >
              {r.thumbnail_url && (
                <img
                  src={r.thumbnail_url}
                  alt={r.title}
                  className="w-full h-40 object-cover"
                />
              )}
              <div className="p-3">
                <p className="font-medium text-sm line-clamp-2">{r.title}</p>
                <p className="text-gray-400 text-xs mt-1">{r.artist}</p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-gray-500 text-xs">
                    {formatDuration(r.duration)}
                  </span>
                  <button
                    onClick={() => onAdd(r)}
                    disabled={isAdding}
                    className="px-3 py-1 text-sm bg-green-700 hover:bg-green-600 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isAdding ? "Adding..." : "Add"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
