from pathlib import Path

from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

ROOT = Path('/opt/homelab/navidrome/music/gio')
AUDIO_EXTS = {'.m4a', '.mp3'}

checked = 0
missing_sidecar = 0
missing_embed = 0
missing_both = 0
missing_examples = []

for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        continue
    checked += 1

    lrc = p.with_suffix('.lrc')
    has_sidecar = lrc.exists()

    has_embed = False
    if p.suffix.lower() == '.m4a':
        tags = MP4(str(p)).tags or {}
        lyr = tags.get('\xa9lyr') or []
        has_embed = bool(lyr and str(lyr[0]).strip())
    elif p.suffix.lower() == '.mp3':
        tags = MP3(str(p), ID3=ID3).tags or {}
        uslt = tags.getall('USLT') if hasattr(tags, 'getall') else []
        has_embed = bool(uslt and str(uslt[0].text).strip())

    if not has_sidecar:
        missing_sidecar += 1
    if not has_embed:
        missing_embed += 1
    if not has_sidecar and not has_embed:
        missing_both += 1
        if len(missing_examples) < 40:
            missing_examples.append(str(p))

print(f'Checked: {checked}')
print(f'Missing sidecar .lrc: {missing_sidecar}')
print(f'Missing embedded lyrics: {missing_embed}')
print(f'Missing both: {missing_both}')
print('Examples missing both:')
for e in missing_examples:
    print(e)
