import re
from collections import Counter, defaultdict
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TDRC, TPE2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

ROOT = Path('/opt/homelab/navidrome/music/gio')
EXTS = {'.m4a', '.mp3', '.flac'}


def extract_year(value: str) -> str:
    m = re.search(r'(19\d{2}|20\d{2})', str(value or ''))
    return m.group(1) if m else ''


def folder_year(name: str) -> str:
    m = re.search(r'\((19\d{2}|20\d{2})\)\s*$', name)
    return m.group(1) if m else ''


def clean_album_from_folder(name: str) -> str:
    return re.sub(r'\s*\((19\d{2}|20\d{2})\)\s*$', '', name).strip()


by_folder = defaultdict(list)
for p in ROOT.rglob('*'):
    if p.is_file() and p.suffix.lower() in EXTS:
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0].lower() == 'singles':
            continue
        by_folder[p.parent].append(p)

changed_files = 0
changed_folders = 0

for folder, files in sorted(by_folder.items()):
    if len(files) <= 1:
        continue

    album_candidates = []
    album_artist_candidates = []
    year_candidates = []

    for p in files:
        ext = p.suffix.lower()
        if ext == '.m4a':
            tags = MP4(str(p)).tags or {}
            album_candidates.append(str((tags.get('\xa9alb') or [''])[0]).strip())
            album_artist_candidates.append(str((tags.get('aART') or tags.get('\xa9ART') or [''])[0]).strip())
            year_candidates.append(extract_year(str((tags.get('\xa9day') or [''])[0]).strip()))
        elif ext == '.mp3':
            tags = MP3(str(p), ID3=ID3).tags or {}
            a = tags.get('TALB'); aa = tags.get('TPE2'); y = tags.get('TDRC')
            album_candidates.append(str(a.text[0]).strip() if a and getattr(a, 'text', None) else '')
            album_artist_candidates.append(str(aa.text[0]).strip() if aa and getattr(aa, 'text', None) else '')
            year_candidates.append(extract_year(str(y.text[0]).strip()) if y and getattr(y, 'text', None) else '')
        elif ext == '.flac':
            tags = FLAC(str(p))
            album_candidates.append((tags.get('album') or [''])[0].strip())
            album_artist_candidates.append((tags.get('albumartist') or tags.get('artist') or [''])[0].strip())
            year_candidates.append(extract_year((tags.get('date') or tags.get('year') or [''])[0].strip()))

    album_candidates = [x for x in album_candidates if x]
    album_artist_candidates = [x for x in album_artist_candidates if x]
    year_candidates = [x for x in year_candidates if x]

    canonical_album = clean_album_from_folder(folder.name) or (Counter(album_candidates).most_common(1)[0][0] if album_candidates else 'Singles')
    canonical_album_artist = Counter(album_artist_candidates).most_common(1)[0][0] if album_artist_candidates else folder.parent.name
    canonical_year = folder_year(folder.name) or (Counter(year_candidates).most_common(1)[0][0] if year_candidates else '')

    folder_changed = False
    for p in files:
        ext = p.suffix.lower()
        if ext == '.m4a':
            audio = MP4(str(p))
            tags = audio.tags or {}
            tags['\xa9alb'] = [canonical_album]
            tags['aART'] = [canonical_album_artist]
            if canonical_year:
                tags['\xa9day'] = [canonical_year]
            audio.save()
            changed_files += 1
            folder_changed = True
        elif ext == '.mp3':
            audio = MP3(str(p), ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(TALB(encoding=3, text=[canonical_album]))
            audio.tags.add(TPE2(encoding=3, text=[canonical_album_artist]))
            if canonical_year:
                audio.tags.add(TDRC(encoding=3, text=[canonical_year]))
            audio.save(v2_version=3)
            changed_files += 1
            folder_changed = True
        elif ext == '.flac':
            audio = FLAC(str(p))
            audio['album'] = canonical_album
            audio['albumartist'] = canonical_album_artist
            if canonical_year:
                audio['date'] = canonical_year
            audio.save()
            changed_files += 1
            folder_changed = True

    if folder_changed:
        changed_folders += 1
        print(f'UPDATED: {folder}')

print(f'Folders changed: {changed_folders}')
print(f'Files rewritten: {changed_files}')
