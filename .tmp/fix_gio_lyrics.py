import os
import re
import signal
from pathlib import Path

# syncedlyrics/platformdirs can fall back to /.cache when HOME is unset.
os.environ["HOME"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"

import syncedlyrics
from mutagen.id3 import ID3, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

ROOT = Path('/opt/homelab/navidrome/music/gio')
AUDIO_EXTS = {'.m4a', '.mp3'}


def normalize_text(value: str, default: str = '') -> str:
    value = re.sub(r'\s+', ' ', str(value or '')).strip()
    return value if value else default


def parse_lrc_timed_lines(lyrics: str) -> int:
    count = 0
    for line in (lyrics or '').splitlines():
        if re.search(r'\[\d+:\d+(?:\.\d+)?\]', line):
            count += 1
    return count


def strip_lrc_timestamps(lyrics: str) -> str:
    plain = []
    for raw in (lyrics or '').splitlines():
        line = re.sub(r'\[[^\]]+\]', '', raw).strip()
        if line:
            plain.append(line)
    return '\n'.join(plain).strip()


def metadata_for_search(path: Path) -> str:
    fallback = path.stem
    ext = path.suffix.lower()
    title = fallback
    artist = ''
    if ext == '.m4a':
        mp4 = MP4(str(path))
        title = normalize_text((mp4.get('\xa9nam') or [title])[0], title)
        artist = normalize_text((mp4.get('\xa9ART') or mp4.get('aART') or [artist])[0], '')
    elif ext == '.mp3':
        mp3 = MP3(str(path), ID3=ID3)
        tags = mp3.tags or {}
        tit = tags.get('TIT2')
        art = tags.get('TPE1') or tags.get('TPE2')
        if tit is not None and getattr(tit, 'text', None):
            title = normalize_text(tit.text[0], title)
        if art is not None and getattr(art, 'text', None):
            artist = normalize_text(art.text[0], '')
    return f'{title} {artist}'.strip() or fallback


def existing_plain_lyrics(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == '.m4a':
        mp4 = MP4(str(path))
        lyr = mp4.get('\xa9lyr') or []
        return normalize_text(lyr[0], '') if lyr else ''
    if ext == '.mp3':
        mp3 = MP3(str(path), ID3=ID3)
        tags = mp3.tags or {}
        uslt = tags.getall('USLT') if hasattr(tags, 'getall') else []
        if uslt:
            return normalize_text(uslt[0].text, '')
    return ''


def write_sidecar_lrc(path: Path, lyrics: str) -> None:
    lrc = path.with_suffix('.lrc')
    lrc.write_text(lyrics, encoding='utf-8')


def embed_lyrics(path: Path, plain_lyrics: str) -> None:
    if path.suffix.lower() == '.m4a':
        mp4 = MP4(str(path))
        mp4['\xa9lyr'] = [plain_lyrics]
        mp4.save()
    elif path.suffix.lower() == '.mp3':
        mp3 = MP3(str(path), ID3=ID3)
        if mp3.tags is None:
            mp3.add_tags()
        mp3.tags.delall('USLT')
        mp3.tags.add(USLT(encoding=3, lang='eng', desc='', text=plain_lyrics))
        mp3.save(v2_version=3)


def should_refresh(path: Path) -> bool:
    lrc = path.with_suffix('.lrc')
    plain = existing_plain_lyrics(path)

    if not lrc.exists():
        return True

    try:
        lrc_text = lrc.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return True

    timed = parse_lrc_timed_lines(lrc_text)
    if timed < 3:
        return True

    if len(plain) < 30:
        return True

    return False


def fetch_synced(search_term: str):
    def _timeout_handler(signum, frame):
        raise TimeoutError()

    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(8)
        return syncedlyrics.search(search_term, synced_only=True)
    except TimeoutError:
        return None
    except Exception:
        return None
    finally:
        signal.alarm(0)


checked = 0
updated = 0
missing = 0
missing_examples = []
for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        continue

    checked += 1
    if not should_refresh(p):
        continue

    term = metadata_for_search(p)
    synced = fetch_synced(term)
    if not synced:
        missing += 1
        if len(missing_examples) < 25:
            missing_examples.append(str(p))
        continue

    plain = strip_lrc_timestamps(synced)
    if len(plain) < 20:
        missing += 1
        if len(missing_examples) < 25:
            missing_examples.append(str(p))
        continue

    write_sidecar_lrc(p, synced)
    embed_lyrics(p, plain)
    updated += 1
    print(f'LYRICS UPDATED: {p}')

print(f'Checked: {checked}')
print(f'Lyrics updated: {updated}')
print(f'Still missing/uncertain: {missing}')
if missing_examples:
    print('Missing examples:')
    for path in missing_examples:
        print(path)
