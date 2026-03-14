import os
import re
import signal
from pathlib import Path

os.environ['HOME'] = '/tmp'
os.environ['XDG_CACHE_HOME'] = '/tmp/.cache'

import syncedlyrics
from mutagen.id3 import ID3, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

ROOT = Path('/opt/homelab/navidrome/music/gio')
AUDIO_EXTS = {'.m4a', '.mp3'}


def normalize_text(value: str, default: str = '') -> str:
    value = re.sub(r'\s+', ' ', str(value or '')).strip()
    return value if value else default


def strip_timestamps(lyrics: str) -> str:
    out = []
    for raw in (lyrics or '').splitlines():
        line = re.sub(r'\[[^\]]+\]', '', raw).strip()
        if line:
            out.append(line)
    return '\n'.join(out).strip()


def timed_lines_count(lyrics: str) -> int:
    return sum(1 for line in (lyrics or '').splitlines() if re.search(r'\[\d+:\d+(?:\.\d+)?\]', line))


def has_embed(path: Path) -> bool:
    if path.suffix.lower() == '.m4a':
        tags = MP4(str(path)).tags or {}
        lyr = tags.get('\xa9lyr') or []
        return bool(lyr and str(lyr[0]).strip())
    tags = MP3(str(path), ID3=ID3).tags or {}
    uslt = tags.getall('USLT') if hasattr(tags, 'getall') else []
    return bool(uslt and str(uslt[0].text).strip())


def search_terms(path: Path):
    title = path.stem
    artist = ''
    if path.suffix.lower() == '.m4a':
        tags = MP4(str(path)).tags or {}
        title = normalize_text((tags.get('\xa9nam') or [title])[0], title)
        artist = normalize_text((tags.get('\xa9ART') or tags.get('aART') or [''])[0], '')
    elif path.suffix.lower() == '.mp3':
        tags = MP3(str(path), ID3=ID3).tags or {}
        t = tags.get('TIT2')
        a = tags.get('TPE1') or tags.get('TPE2')
        if t is not None and getattr(t, 'text', None):
            title = normalize_text(t.text[0], title)
        if a is not None and getattr(a, 'text', None):
            artist = normalize_text(a.text[0], '')

    clean_title = re.sub(r'^\d+\s*-\s*', '', title).strip()
    terms = []
    if artist:
        terms.append(f'{clean_title} {artist}')
    terms.append(clean_title)
    if ' - ' in clean_title:
        terms.append(clean_title.split(' - ', 1)[1].strip())
    return [t for t in dict.fromkeys([x.strip() for x in terms if x.strip()])]


def fetch_synced(term: str):
    def _timeout_handler(signum, frame):
        raise TimeoutError()

    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(8)
        return syncedlyrics.search(term, synced_only=True)
    except Exception:
        return None
    finally:
        signal.alarm(0)


def write_lyrics(path: Path, synced: str, plain: str):
    path.with_suffix('.lrc').write_text(synced, encoding='utf-8')
    if path.suffix.lower() == '.m4a':
        audio = MP4(str(path))
        audio['\xa9lyr'] = [plain]
        audio.save()
    else:
        audio = MP3(str(path), ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall('USLT')
        audio.tags.add(USLT(encoding=3, lang='eng', desc='', text=plain))
        audio.save(v2_version=3)


checked = 0
fixed = 0
still_missing = []

for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        continue

    lrc = p.with_suffix('.lrc')
    if lrc.exists() or has_embed(p):
        continue

    checked += 1
    synced = None
    for term in search_terms(p):
        synced = fetch_synced(term)
        if synced and timed_lines_count(synced) >= 2:
            break
    if not synced:
        still_missing.append(str(p))
        continue

    plain = strip_timestamps(synced)
    if len(plain) < 20:
        still_missing.append(str(p))
        continue

    write_lyrics(p, synced, plain)
    fixed += 1
    print(f'FIXED: {p}')

print(f'Checked missing tracks: {checked}')
print(f'Fixed: {fixed}')
print(f'Remaining missing: {len(still_missing)}')
for p in still_missing[:40]:
    print(p)
