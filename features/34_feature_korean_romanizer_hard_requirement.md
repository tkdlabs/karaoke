# Feature 34: Make korean_romanizer a hard dependency

## Description

`korean_romanizer` is currently an optional dependency pulled in via
`karaoke-workflows[korean]`. The optional-import pattern (`try/except ImportError`,
`HAS_KOREAN_ROMANIZER` flag) has been bug-prone in practice and adds complexity
to both the server code and tests.

Since romanization is a first-class feature (used by the lyrics API endpoint and
the overlay renderer, and expected by the karaoke-tv native LRC renderer), it
should be a hard requirement like any other dependency.

## Changes

- Remove `HAS_KOREAN_ROMANIZER` guard from `karaoke_workflows/lyrics.py`
- Remove the `[korean]` optional extra from `workflows/karaoke/pyproject.toml`;
  move `korean_romanizer` into the base dependencies
- Update `frontends/karaoke/server/requirements.txt` and `pyproject.toml`
  to depend on `karaoke-workflows` (not `karaoke-workflows[korean]`)
- Remove the `HAS_KOREAN_ROMANIZER` stub from `tests/conftest.py`
- Remove `HAS_KOREAN_ROMANIZER`-related test branches

## Acceptance criteria

- [ ] `korean_romanizer` is in the base deps of `karaoke-workflows`
- [ ] `HAS_KOREAN_ROMANIZER` flag and try/except import removed from `lyrics.py`
- [ ] `romanize_korean` always available — no optional guard
- [ ] All existing tests pass
- [ ] Deploy docs / requirements updated
