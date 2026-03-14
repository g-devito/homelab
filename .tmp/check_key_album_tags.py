from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

checks = [
    Path('/opt/homelab/navidrome/music/gio/Gesaffelstein/Aleph'),
    Path('/opt/homelab/navidrome/music/gio/Carpenter Brut/Furi (Original Game Soundtrack)'),
    Path('/opt/homelab/navidrome/music/gio/Caparezza/Prisoner 709 (2017)'),
]

for folder in checks:
    years = set()
    albums = set()
    album_artists = set()
    count = 0

    for p in sorted(folder.glob('*')):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == '.flac':
            tags = FLAC(str(p))
            years.add((tags.get('date') or tags.get('year') or [''])[0])
            albums.add((tags.get('album') or [''])[0])
            album_artists.add((tags.get('albumartist') or [''])[0])
            count += 1
        elif ext == '.mp3':
            tags = MP3(str(p), ID3=ID3).tags or {}
            y = tags.get('TDRC')
            a = tags.get('TALB')
            aa = tags.get('TPE2')
            years.add(str(y.text[0]) if y and getattr(y, 'text', None) else '')
            albums.add(str(a.text[0]) if a and getattr(a, 'text', None) else '')
            album_artists.add(str(aa.text[0]) if aa and getattr(aa, 'text', None) else '')
            count += 1

    years = sorted([x for x in years if x])
    albums = sorted([x for x in albums if x])
    album_artists = sorted([x for x in album_artists if x])
    print(folder)
    print(f' tracks={count}')
    print(f' years={years}')
    print(f' album={albums}')
    print(f' album_artist={album_artists}')
