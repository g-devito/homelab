import re
from collections import Counter, defaultdict
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TDRC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

root = Path('/opt/homelab/navidrome/music/gio')
exts = {'.m4a', '.mp3', '.flac'}


def extract_year(value: str) -> str:
    m = re.search(r'(19\d{2}|20\d{2})', str(value or ''))
    return m.group(1) if m else ''


def folder_year(folder_name: str) -> str:
    m = re.search(r'\((19\d{2}|20\d{2})\)', folder_name)
    return m.group(1) if m else ''


def clean_folder_album_name(folder_name: str) -> str:
    return re.sub(r'\s*\((19\d{2}|20\d{2})\)\s*$', '', folder_name).strip()


albums = defaultdict(list)
for p in root.rglob('*'):
    if p.is_file() and p.suffix.lower() in exts:
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0].lower() == 'singles':
            continue
        albums[str(p.parent)].append(p)

updated = 0
folders_touched = 0

for folder, files in sorted(albums.items()):
    if len(files) <= 1:
        continue

    folder_path = Path(folder)
    folder_album_name = clean_folder_album_name(folder_path.name)
    folder_artist_name = folder_path.parent.name if folder_path.parent != root else ''
    folder_year_hint = folder_year(folder_path.name)

    album_vals = []
    aartist_vals = []
    artist_vals = []
    year_vals = []

    per_file = []
    for p in files:
        ext = p.suffix.lower()
        row = {
            'path': p,
            'ext': ext,
            'album': '',
            'album_artist': '',
            'artist': '',
            'year': '',
        }

        try:
            if ext == '.m4a':
                tags = MP4(str(p)).tags or {}
                row['album'] = str((tags.get('\xa9alb') or [''])[0]).strip()
                row['artist'] = str((tags.get('\xa9ART') or [''])[0]).strip()
                row['album_artist'] = str((tags.get('aART') or [''])[0]).strip()
                row['year'] = extract_year(str((tags.get('\xa9day') or [''])[0]).strip())
            elif ext == '.mp3':
                tags = MP3(str(p), ID3=ID3).tags or {}
                alb = tags.get('TALB')
                ar = tags.get('TPE1')
                aa = tags.get('TPE2')
                y = tags.get('TDRC')
                row['album'] = str(alb.text[0]).strip() if isinstance(alb, TALB) and alb.text else ''
                row['artist'] = str(ar.text[0]).strip() if ar and getattr(ar, 'text', None) else ''
                row['album_artist'] = str(aa.text[0]).strip() if isinstance(aa, TPE2) and aa.text else ''
                row['year'] = extract_year(str(y.text[0]).strip()) if isinstance(y, TDRC) and y.text else ''
            elif ext == '.flac':
                tags = FLAC(str(p))
                row['album'] = (tags.get('album') or [''])[0].strip()
                row['artist'] = (tags.get('artist') or [''])[0].strip()
                row['album_artist'] = (tags.get('albumartist') or [''])[0].strip()
                row['year'] = extract_year((tags.get('date') or tags.get('year') or [''])[0].strip())
        except Exception:
            pass

        if row['album']:
            album_vals.append(row['album'])
        if row['album_artist']:
            aartist_vals.append(row['album_artist'])
        if row['artist']:
            artist_vals.append(row['artist'])
        if row['year']:
            year_vals.append(row['year'])

        per_file.append(row)

    if not per_file:
        continue

    canon_album = Counter(album_vals).most_common(1)[0][0] if album_vals else folder_album_name
    if folder_album_name:
        canon_album = folder_album_name

    unique_track_artists = sorted({a for a in artist_vals if a})
    canon_album_artist = ''
    if aartist_vals:
        canon_album_artist = Counter(aartist_vals).most_common(1)[0][0]
    if not canon_album_artist:
        if len(unique_track_artists) == 1:
            canon_album_artist = unique_track_artists[0]
        elif len(unique_track_artists) > 1:
            canon_album_artist = 'Various Artists'
        else:
            canon_album_artist = folder_artist_name or 'Unknown Artist'

    canon_year = folder_year_hint or (Counter(year_vals).most_common(1)[0][0] if year_vals else '')

    folder_changed = False
    for row in per_file:
        p = row['path']
        ext = row['ext']
        try:
            if ext == '.m4a':
                audio = MP4(str(p))
                tags = audio.tags or {}
                before = (
                    str((tags.get('\xa9alb') or [''])[0]).strip(),
                    str((tags.get('aART') or [''])[0]).strip(),
                    extract_year(str((tags.get('\xa9day') or [''])[0]).strip()),
                )

                tags['\xa9alb'] = [canon_album]
                tags['aART'] = [canon_album_artist]
                if canon_year:
                    tags['\xa9day'] = [canon_year]
                if canon_album_artist == 'Various Artists':
                    tags['cpil'] = [1]
                elif 'cpil' in tags:
                    del tags['cpil']

                after = (canon_album, canon_album_artist, canon_year)
                if before != after:
                    audio.save()
                    updated += 1
                    folder_changed = True

            elif ext == '.mp3':
                audio = MP3(str(p), ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
                tags = audio.tags

                alb = tags.get('TALB')
                aa = tags.get('TPE2')
                y = tags.get('TDRC')
                before = (
                    str(alb.text[0]).strip() if isinstance(alb, TALB) and alb.text else '',
                    str(aa.text[0]).strip() if isinstance(aa, TPE2) and aa.text else '',
                    extract_year(str(y.text[0]).strip()) if isinstance(y, TDRC) and y.text else '',
                )

                tags.add(TALB(encoding=3, text=[canon_album]))
                tags.add(TPE2(encoding=3, text=[canon_album_artist]))
                if canon_year:
                    tags.add(TDRC(encoding=3, text=[canon_year]))

                after = (canon_album, canon_album_artist, canon_year)
                if before != after:
                    audio.save(v2_version=3)
                    updated += 1
                    folder_changed = True

            elif ext == '.flac':
                audio = FLAC(str(p))
                before = (
                    (audio.get('album') or [''])[0].strip(),
                    (audio.get('albumartist') or [''])[0].strip(),
                    extract_year((audio.get('date') or [''])[0] if audio.get('date') else ''),
                )

                audio['album'] = canon_album
                audio['albumartist'] = canon_album_artist
                if canon_year:
                    audio['date'] = canon_year

                after = (canon_album, canon_album_artist, canon_year)
                if before != after:
                    audio.save()
                    updated += 1
                    folder_changed = True
        except Exception:
            continue

    if folder_changed:
        folders_touched += 1
        print(f'UPDATED folder: {folder_path}')

print(f'Folders touched: {folders_touched}')
print(f'Files updated: {updated}')
