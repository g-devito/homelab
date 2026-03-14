from pathlib import Path
from collections import defaultdict

from mutagen.id3 import ID3, TALB, TDRC, TPE1, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC

root = Path('/opt/homelab/navidrome/music/gio')
exts = {'.m4a', '.mp3', '.flac'}

albums = defaultdict(list)
for p in root.rglob('*'):
    if p.is_file() and p.suffix.lower() in exts:
        albums[str(p.parent)].append(p)

print(f'Folders scanned: {len(albums)}')
print('Potential split folders:')

for folder, files in sorted(albums.items()):
    vals = {
        'album': set(),
        'artist': set(),
        'album_artist': set(),
        'year': set(),
        'disk': set(),
    }

    for p in files:
        ext = p.suffix.lower()
        if ext == '.m4a':
            tags = MP4(str(p)).tags or {}
            vals['album'].add(str((tags.get('\xa9alb') or [''])[0]).strip())
            vals['artist'].add(str((tags.get('\xa9ART') or [''])[0]).strip())
            vals['album_artist'].add(str((tags.get('aART') or [''])[0]).strip())
            vals['year'].add(str((tags.get('\xa9day') or [''])[0]).strip())
            vals['disk'].add(str((tags.get('disk') or [(0, 0)])[0]))
        elif ext == '.mp3':
            tags = MP3(str(p), ID3=ID3).tags or {}
            alb = tags.get('TALB')
            art = tags.get('TPE1')
            aart = tags.get('TPE2')
            year = tags.get('TDRC')
            vals['album'].add(str(alb.text[0]).strip() if isinstance(alb, TALB) and alb.text else '')
            vals['artist'].add(str(art.text[0]).strip() if isinstance(art, TPE1) and art.text else '')
            vals['album_artist'].add(str(aart.text[0]).strip() if isinstance(aart, TPE2) and aart.text else '')
            vals['year'].add(str(year.text[0]).strip() if isinstance(year, TDRC) and year.text else '')
        elif ext == '.flac':
            tags = FLAC(str(p))
            vals['album'].add((tags.get('album') or [''])[0].strip())
            vals['artist'].add((tags.get('artist') or [''])[0].strip())
            vals['album_artist'].add((tags.get('albumartist') or [''])[0].strip())
            vals['year'].add((tags.get('date') or tags.get('year') or [''])[0].strip())
            disc = (tags.get('discnumber') or [''])[0].strip()
            vals['disk'].add(disc)

    nz = {k: sorted([x for x in v if x]) for k, v in vals.items()}
    reasons = []
    for key in ('album', 'album_artist', 'year', 'disk'):
        if len(nz[key]) > 1:
            reasons.append(f'{key}={len(nz[key])}')

    if reasons:
        print(f'- {folder} | tracks={len(files)} | ' + '; '.join(reasons))
        print(f"  album={nz['album'][:4]}")
        print(f"  album_artist={nz['album_artist'][:6]}")
        print(f"  year={nz['year'][:6]} disk={nz['disk'][:6]}")
