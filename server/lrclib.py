"""lrclib.net lyrics search wrapper."""

from lrcup import LRCLib

from models import LyricsSearchResult


def search(query: str, duration: float | None = None) -> list[LyricsSearchResult]:
    """
    Search lrclib.net for lyrics.

    Results are sorted: synced lyrics first, then by closest duration match.
    """
    client = LRCLib()
    results = client.search(query=query)

    if not results:
        return []

    def _sort_key(track):
        has_synced = bool(track.syncedLyrics)
        duration_diff = abs(track.duration - duration) if duration else 0
        return (not has_synced, duration_diff)

    results = sorted(results, key=_sort_key)

    out = []
    for track in results:
        if track.syncedLyrics:
            lyrics_type = "synced"
        elif track.plainLyrics:
            lyrics_type = "plain"
        elif track.instrumental:
            lyrics_type = "instrumental"
        else:
            lyrics_type = "none"

        # Preview: first 3 non-empty lines
        content = track.syncedLyrics or track.plainLyrics or ""
        preview_lines = [l for l in content.strip().split("\n") if l.strip()][:3]

        out.append(LyricsSearchResult(
            track_id=track.id,
            track_name=track.trackName,
            artist_name=track.artistName,
            album_name=track.albumName,
            duration=track.duration,
            lyrics_type=lyrics_type,
            synced_lyrics=track.syncedLyrics,
            plain_lyrics=track.plainLyrics,
            preview=preview_lines,
        ))

    return out
