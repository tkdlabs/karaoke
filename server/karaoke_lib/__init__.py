"""Self-contained karaoke processing helpers, folded into the server.

This package replaces the external `karaoke_workflows` dependency
(formally workflows/karaoke) so the project is fully self-contained:
lyrics parsing/romanization (`lyrics.py`) and lyrics-overlay video
rendering (`video.py`). MIT licensed, see LICENSE.
"""