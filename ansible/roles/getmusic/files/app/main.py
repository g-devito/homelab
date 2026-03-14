import os
# Force a writable HOME so syncedlyrics/platformdirs don't try to write to /.cache
# (uid 1000 has no /etc/passwd entry in this image, so HOME is unset or resolves to /)
os.environ["HOME"] = "/tmp"
from collections import Counter
import re
import shlex
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue
from typing import Dict, List, Optional, Tuple

import syncedlyrics
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, SYLT, USLT
from mutagen.mp4 import MP4, MP4Cover
from mutagen.mp3 import MP3

APP_TITLE = "GetMusic"
MUSIC_ROOT = os.getenv("GETMUSIC_MUSIC_ROOT", "/opt/homelab/navidrome/music")
DOWNLOAD_TMP_ROOT = "/downloads"

app = FastAPI(title=APP_TITLE)


@dataclass
class Job:
    id: str
    url: str
    navidrome_user: str
    output_format: str
    embed_lyrics: bool
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    downloaded_files: List[str] = field(default_factory=list)
    error: Optional[str] = None


jobs: Dict[str, Job] = {}
job_queue: "Queue[str]" = Queue()
jobs_lock = threading.Lock()


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def sanitize_segment(value: str, default: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^a-zA-Z0-9._ -]", "_", value)
    value = value.strip(" .")
    return value or default


def normalize_text(value: str, default: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if value else default


def extract_year(value: str) -> str:
    m = re.search(r"(19\d{2}|20\d{2})", str(value or ""))
    return m.group(1) if m else ""


def primary_artist(artist_str: str) -> str:
    """Return only the first/main artist, stripping featured guests."""
    # Strip feat./ft./featuring/with collaborations
    artist_str = re.split(r"\s+(?:feat\.?|ft\.?|featuring|with)\s+", artist_str, flags=re.IGNORECASE)[0]
    artist_str = re.split(r"[,;]", artist_str)[0]
    return artist_str.strip()


def parse_track_number(value: str) -> int:
    if not value:
        return 0
    m = re.match(r"^(\d+)", str(value).strip())
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def unique_destination(path: str) -> str:
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{root} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def extract_audio_metadata(audio_path: str) -> Tuple[str, str, str, int]:
    ext = os.path.splitext(audio_path)[1].lower()
    fallback_title = os.path.splitext(os.path.basename(audio_path))[0]
    artist = "Unknown Artist"
    album = "Singles"
    title = fallback_title
    track_no = 0

    if ext == ".m4a":
        mp4 = MP4(audio_path)
        # Prefer album artist (aART) for folder organisation; fall back to
        # track artist (©ART). Always strip guest artists from both.
        album_artist_raw = (mp4.get("aART") or [""])[0] or ""
        track_artist_raw = (mp4.get("\xa9ART") or [""])[0] or ""
        artist = primary_artist(album_artist_raw) or primary_artist(track_artist_raw) or artist
        album = (mp4.get("\xa9alb") or [album])[0] or album
        title = (mp4.get("\xa9nam") or [title])[0] or title
        trkn = mp4.get("trkn") or []
        if trkn and isinstance(trkn[0], tuple):
            track_no = int(trkn[0][0] or 0)
    elif ext == ".mp3":
        mp3 = MP3(audio_path, ID3=ID3)
        tags = mp3.tags
        if tags:
            # TPE2 = album artist, TPE1 = track artist
            album_artist_frame = tags.get("TPE2")
            track_artist_frame = tags.get("TPE1")
            album_frame = tags.get("TALB")
            title_frame = tags.get("TIT2")
            track_frame = tags.get("TRCK")

            album_artist_raw = ""
            track_artist_raw = ""
            if isinstance(album_artist_frame, TPE2) and album_artist_frame.text:
                album_artist_raw = album_artist_frame.text[0]
            if isinstance(track_artist_frame, TPE1) and track_artist_frame.text:
                track_artist_raw = track_artist_frame.text[0]
            artist = primary_artist(album_artist_raw) or primary_artist(track_artist_raw) or artist
            if isinstance(album_frame, TALB) and album_frame.text:
                album = album_frame.text[0]
            if isinstance(title_frame, TIT2) and title_frame.text:
                title = title_frame.text[0]
            if isinstance(track_frame, TRCK) and track_frame.text:
                track_no = parse_track_number(track_frame.text[0])

    artist = sanitize_segment(str(artist), "Unknown Artist")
    album = sanitize_segment(str(album), "Singles")
    title = sanitize_segment(str(title), fallback_title)
    return artist, album, title, track_no


def metadata_for_search(audio_path: str) -> str:
    ext = os.path.splitext(audio_path)[1].lower()
    fallback = os.path.splitext(os.path.basename(audio_path))[0]
    title = fallback
    artist = ""

    try:
        if ext == ".m4a":
            mp4 = MP4(audio_path)
            title = normalize_text((mp4.get("\xa9nam") or [title])[0], title)
            artist = normalize_text((mp4.get("\xa9ART") or mp4.get("aART") or [artist])[0], "")
        elif ext == ".mp3":
            mp3 = MP3(audio_path, ID3=ID3)
            tags = mp3.tags
            if tags:
                title_frame = tags.get("TIT2")
                artist_frame = tags.get("TPE1") or tags.get("TPE2")
                if isinstance(title_frame, TIT2) and title_frame.text:
                    title = normalize_text(title_frame.text[0], title)
                if isinstance(artist_frame, (TPE1, TPE2)) and artist_frame.text:
                    artist = normalize_text(artist_frame.text[0], "")
    except Exception:
        return fallback

    return f"{title} {artist}".strip() or fallback


def metadata_search_terms(audio_path: str) -> List[str]:
    primary = metadata_for_search(audio_path)
    title = os.path.splitext(os.path.basename(audio_path))[0]

    try:
        ext = os.path.splitext(audio_path)[1].lower()
        if ext == ".m4a":
            mp4 = MP4(audio_path)
            title = normalize_text((mp4.get("\xa9nam") or [title])[0], title)
        elif ext == ".mp3":
            mp3 = MP3(audio_path, ID3=ID3)
            tags = mp3.tags
            if tags:
                title_frame = tags.get("TIT2")
                if isinstance(title_frame, TIT2) and title_frame.text:
                    title = normalize_text(title_frame.text[0], title)
    except Exception:
        pass

    title = re.sub(r"^\d+\s*-\s*", "", title).strip()
    variants = [primary, title]
    if " - " in title:
        variants.append(title.split(" - ", 1)[1].strip())
    if "(" in title:
        variants.append(re.sub(r"\s*\([^)]*\)", "", title).strip())

    unique_terms: List[str] = []
    seen = set()
    for candidate in variants:
        candidate = normalize_text(candidate, "")
        if candidate and candidate not in seen:
            unique_terms.append(candidate)
            seen.add(candidate)
    return unique_terms


def normalize_m4a_metadata(audio_path: str) -> None:
    audio = MP4(audio_path)
    fallback_title = os.path.splitext(os.path.basename(audio_path))[0]

    title = normalize_text((audio.get("\xa9nam") or [fallback_title])[0], fallback_title)
    artist = normalize_text((audio.get("\xa9ART") or audio.get("aART") or ["Unknown Artist"])[0], "Unknown Artist")
    album = normalize_text((audio.get("\xa9alb") or ["Singles"])[0], "Singles")
    album_artist = normalize_text((audio.get("aART") or [artist])[0], artist)
    genre = normalize_text((audio.get("\xa9gen") or [""])[0], "")
    year = extract_year((audio.get("\xa9day") or [""])[0])

    track_no = 0
    total_tracks = 0
    trkn = audio.get("trkn") or []
    if trkn and isinstance(trkn[0], tuple):
        track_no = int(trkn[0][0] or 0)
        total_tracks = int(trkn[0][1] or 0)

    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [artist]
    audio["aART"] = [album_artist]
    audio["\xa9alb"] = [album]
    if track_no > 0:
        audio["trkn"] = [(track_no, total_tracks)]
    if year:
        audio["\xa9day"] = [year]
    if genre:
        audio["\xa9gen"] = [genre]

    audio.save()


def normalize_mp3_metadata(audio_path: str) -> None:
    audio = MP3(audio_path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags
    fallback_title = os.path.splitext(os.path.basename(audio_path))[0]

    artist_frame = tags.get("TPE1") or tags.get("TPE2")
    album_frame = tags.get("TALB")
    title_frame = tags.get("TIT2")
    track_frame = tags.get("TRCK")
    genre_frame = tags.get("TCON")
    year_frame = tags.get("TDRC")

    title = normalize_text(title_frame.text[0] if isinstance(title_frame, TIT2) and title_frame.text else fallback_title, fallback_title)
    artist = normalize_text(artist_frame.text[0] if isinstance(artist_frame, (TPE1, TPE2)) and artist_frame.text else "Unknown Artist", "Unknown Artist")
    album = normalize_text(album_frame.text[0] if isinstance(album_frame, TALB) and album_frame.text else "Singles", "Singles")
    genre = normalize_text(genre_frame.text[0] if isinstance(genre_frame, TCON) and genre_frame.text else "", "")
    year = extract_year(year_frame.text[0] if isinstance(year_frame, TDRC) and year_frame.text else "")
    track_no = parse_track_number(track_frame.text[0] if isinstance(track_frame, TRCK) and track_frame.text else "")

    tags.add(TIT2(encoding=3, text=[title]))
    tags.add(TPE1(encoding=3, text=[artist]))
    tags.add(TPE2(encoding=3, text=[artist]))
    tags.add(TALB(encoding=3, text=[album]))
    if track_no > 0:
        tags.add(TRCK(encoding=3, text=[str(track_no)]))
    if genre:
        tags.add(TCON(encoding=3, text=[genre]))
    if year:
        tags.add(TDRC(encoding=3, text=[year]))

    audio.save(v2_version=3)


def normalize_metadata(audio_path: str) -> None:
    ext = os.path.splitext(audio_path)[1].lower()
    if ext == ".m4a":
        normalize_m4a_metadata(audio_path)
    elif ext == ".mp3":
        normalize_mp3_metadata(audio_path)


def find_sidecar_image(audio_path: str) -> Optional[str]:
    base = os.path.splitext(audio_path)[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def embed_cover_mp3(audio_path: str, image_path: str) -> None:
    with open(image_path, "rb") as f:
        data = f.read()

    mime = "image/jpeg"
    lower = image_path.lower()
    if lower.endswith(".png"):
        mime = "image/png"
    elif lower.endswith(".webp"):
        mime = "image/webp"

    audio = MP3(audio_path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.delall("APIC")
    audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="cover", data=data))
    audio.save(v2_version=3)


def embed_cover_m4a(audio_path: str, image_path: str) -> None:
    with open(image_path, "rb") as f:
        data = f.read()

    fmt = MP4Cover.FORMAT_JPEG
    lower = image_path.lower()
    if lower.endswith(".png"):
        fmt = MP4Cover.FORMAT_PNG

    audio = MP4(audio_path)
    audio["covr"] = [MP4Cover(data, imageformat=fmt)]
    audio.save()


def embed_cover_from_sidecar(audio_path: str) -> Optional[str]:
    image_path = find_sidecar_image(audio_path)
    if not image_path:
        return None

    ext = os.path.splitext(audio_path)[1].lower()
    if ext == ".mp3":
        embed_cover_mp3(audio_path, image_path)
    elif ext == ".m4a":
        embed_cover_m4a(audio_path, image_path)
    else:
        return None

    return image_path


def organize_audio_file(audio_path: str, user_music_dir: str) -> str:
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in {".mp3", ".m4a"}:
        return audio_path

    artist, album, title, track_no = extract_audio_metadata(audio_path)
    target_dir = os.path.join(user_music_dir, artist, album)
    os.makedirs(target_dir, exist_ok=True)

    if track_no > 0:
        filename = f"{track_no:02d} - {title}{ext}"
    else:
        filename = f"{title}{ext}"

    destination = unique_destination(os.path.join(target_dir, filename))
    if os.path.abspath(audio_path) == os.path.abspath(destination):
        return audio_path

    # Keep sidecar lyric/image files with the audio file when moving.
    sidecars = []
    for side_ext in (".lrc", ".srt", ".jpg", ".jpeg", ".png", ".webp"):
        side = os.path.splitext(audio_path)[0] + side_ext
        if os.path.exists(side):
            sidecars.append(side)

    shutil.move(audio_path, destination)
    for side in sidecars:
        moved_side = os.path.splitext(destination)[0] + os.path.splitext(side)[1]
        shutil.move(side, moved_side)

    return destination


def read_album_tuple(audio_path: str) -> Tuple[str, str, str]:
    ext = os.path.splitext(audio_path)[1].lower()
    album = ""
    album_artist = ""
    year = ""

    if ext == ".m4a":
        mp4 = MP4(audio_path)
        album = normalize_text((mp4.get("\xa9alb") or [""])[0], "")
        album_artist = normalize_text((mp4.get("aART") or mp4.get("\xa9ART") or [""])[0], "")
        year = extract_year((mp4.get("\xa9day") or [""])[0])
    elif ext == ".mp3":
        mp3 = MP3(audio_path, ID3=ID3)
        tags = mp3.tags or {}
        album_frame = tags.get("TALB")
        artist_frame = tags.get("TPE2") or tags.get("TPE1")
        year_frame = tags.get("TDRC")
        album = normalize_text(album_frame.text[0] if isinstance(album_frame, TALB) and album_frame.text else "", "")
        album_artist = normalize_text(artist_frame.text[0] if isinstance(artist_frame, (TPE1, TPE2)) and artist_frame.text else "", "")
        year = extract_year(year_frame.text[0] if isinstance(year_frame, TDRC) and year_frame.text else "")

    return album, album_artist, year


def force_album_consistency(organized_files: List[str]) -> None:
    by_folder: Dict[str, List[str]] = {}
    for path in organized_files:
        ext = os.path.splitext(path)[1].lower()
        if ext not in {".m4a", ".mp3"}:
            continue
        folder = os.path.dirname(path)
        by_folder.setdefault(folder, []).append(path)

    for folder, files in by_folder.items():
        if len(files) <= 1:
            continue

        album_values: List[str] = []
        album_artist_values: List[str] = []
        year_values: List[str] = []

        for path in files:
            album, album_artist, year = read_album_tuple(path)
            if album:
                album_values.append(album)
            if album_artist:
                album_artist_values.append(album_artist)
            if year:
                year_values.append(year)

        canonical_album = os.path.basename(folder).strip() or "Singles"
        if album_values:
            canonical_album = Counter(album_values).most_common(1)[0][0]

        canonical_album_artist = ""
        if album_artist_values:
            canonical_album_artist = Counter(album_artist_values).most_common(1)[0][0]

        canonical_year = ""
        if year_values:
            canonical_year = Counter(year_values).most_common(1)[0][0]

        for path in files:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".m4a":
                audio = MP4(path)
                audio["\xa9alb"] = [canonical_album]
                if canonical_album_artist:
                    audio["aART"] = [canonical_album_artist]
                if canonical_year:
                    audio["\xa9day"] = [canonical_year]
                audio.save()
            elif ext == ".mp3":
                audio = MP3(path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
                audio.tags.add(TALB(encoding=3, text=[canonical_album]))
                if canonical_album_artist:
                    audio.tags.add(TPE2(encoding=3, text=[canonical_album_artist]))
                if canonical_year:
                    audio.tags.add(TDRC(encoding=3, text=[canonical_year]))
                audio.save(v2_version=3)


def parse_lrc_synced(lyrics: str) -> List[Tuple[str, int]]:
    timed_lines: List[Tuple[str, int]] = []
    for raw_line in lyrics.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matches = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        text = re.sub(r"\[[^\]]+\]", "", line).strip()
        if not matches or not text:
            continue
        for minute, second in matches:
            total_ms = int((int(minute) * 60 + float(second)) * 1000)
            timed_lines.append((text, total_ms))
    timed_lines.sort(key=lambda x: x[1])
    return timed_lines


def strip_lrc_timestamps(lyrics: str) -> str:
    plain = []
    for raw_line in lyrics.splitlines():
        line = re.sub(r"\[[^\]]+\]", "", raw_line).strip()
        if line:
            plain.append(line)
    return "\n".join(plain).strip()


def write_sidecar_lrc(audio_path: str, lyrics: str) -> str:
    lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lyrics)
    return lrc_path


def embed_lyrics_mp3(audio_path: str, plain_lyrics: str, synced_lyrics: str) -> None:
    audio = MP3(audio_path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    for frame in list(audio.tags.getall("USLT")):
        audio.tags.delall("USLT")
    audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=plain_lyrics))

    timed = parse_lrc_synced(synced_lyrics)
    if timed:
        audio.tags.delall("SYLT")
        audio.tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="synced", text=timed))

    audio.save(v2_version=3)


def embed_lyrics_m4a(audio_path: str, plain_lyrics: str) -> None:
    audio = MP4(audio_path)
    audio["\xa9lyr"] = [plain_lyrics]
    audio.save()


def fetch_synced_lyrics(search_term: str) -> Optional[str]:
    try:
        return syncedlyrics.search(search_term, synced_only=True)
    except Exception:
        return None


def fetch_best_synced_lyrics(audio_path: str) -> Tuple[Optional[str], Optional[str]]:
    for term in metadata_search_terms(audio_path):
        synced = fetch_synced_lyrics(term)
        if synced:
            return synced, term
    return None, None


def build_ytdlp_command(url: str, tmp_dir: str, output_format: str) -> List[str]:
    # Downloads everything into tmp_dir; intermediate .mp4/.webm stay there and are
    # cleaned up after we have collected the final audio files.
    return [
        "yt-dlp",
        "--yes-playlist",
        "--no-warnings",
        "--restrict-filenames",
        "--add-metadata",
        "--embed-metadata",
        "--write-thumbnail",
        "--embed-thumbnail",
        "--convert-thumbnails", "jpg",
        # Keep only the first artist when yt-dlp returns a comma/semicolon-separated list
        "--replace-in-metadata", "artist,album_artist", r"([^,;]+)[,;].*", r"\1",
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "-x", "--audio-format", output_format, "--audio-quality", "0",
        "-P", tmp_dir,
        "-o", "%(autonumber)02d %(title)s.%(ext)s",
        url,
    ]


def process_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.status = "running"
        job.started_at = utc_now()

    user_dir = sanitize_segment(job.navidrome_user, "shared")
    user_music_dir = os.path.join(MUSIC_ROOT, user_dir)
    os.makedirs(user_music_dir, exist_ok=True)

    # All yt-dlp output (audio, thumbnails, intermediates) goes into a per-job temp
    # dir. Only the final audio files are moved to the music library.
    job_tmp_dir = os.path.join(DOWNLOAD_TMP_ROOT, job.id)
    os.makedirs(job_tmp_dir, exist_ok=True)

    cmd = build_ytdlp_command(job.url, job_tmp_dir, job.output_format)
    with jobs_lock:
        job.logs.append("RUN: " + " ".join(shlex.quote(c) for c in cmd))

    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.stdout:
            with jobs_lock:
                job.logs.extend(result.stdout.strip().splitlines())
        if result.stderr:
            with jobs_lock:
                job.logs.extend(result.stderr.strip().splitlines())

        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed with code {result.returncode}")

        # Collect only audio files from the tmp dir; skip .mp4/.webm intermediates,
        # thumbnails, and any other artefacts yt-dlp may leave behind.
        downloaded: List[str] = []
        for root, _, files in os.walk(job_tmp_dir):
            for fname in sorted(files):
                if os.path.splitext(fname)[1].lower() in {".mp3", ".m4a"}:
                    downloaded.append(os.path.join(root, fname))
        downloaded.sort()

        with jobs_lock:
            job.downloaded_files = list(downloaded)
            job.logs.append(f"Downloaded audio files: {len(downloaded)}")

        for audio_path in downloaded:
            try:
                normalize_metadata(audio_path)
            except Exception as exc:
                with jobs_lock:
                    job.logs.append(f"Metadata normalize failed for {audio_path}: {exc}")

        for audio_path in downloaded:
            try:
                side_image = embed_cover_from_sidecar(audio_path)
                if side_image:
                    with jobs_lock:
                        job.logs.append(f"Embedded cover art from {side_image} into {audio_path}")
            except Exception as exc:
                with jobs_lock:
                    job.logs.append(f"Cover embed failed for {audio_path}: {exc}")

        if job.embed_lyrics:
            for audio_path in downloaded:
                ext = os.path.splitext(audio_path)[1].lower()
                if ext not in {".mp3", ".m4a"}:
                    continue

                synced, term = fetch_best_synced_lyrics(audio_path)
                if not synced:
                    with jobs_lock:
                        job.logs.append(f"No synced lyrics found: {metadata_search_terms(audio_path)[0]}")
                    continue

                plain = strip_lrc_timestamps(synced)
                sidecar = write_sidecar_lrc(audio_path, synced)
                with jobs_lock:
                    job.logs.append(f"Lyrics matched using search term: {term}")
                    job.logs.append(f"Saved sidecar lyrics: {sidecar}")

                if ext == ".mp3":
                    embed_lyrics_mp3(audio_path, plain, synced)
                    with jobs_lock:
                        job.logs.append(f"Embedded USLT+SYLT in MP3: {audio_path}")
                elif ext == ".m4a":
                    embed_lyrics_m4a(audio_path, plain)
                    with jobs_lock:
                        job.logs.append(f"Embedded plain lyrics in M4A: {audio_path}")

        # Move audio (+ sidecar .lrc/.jpg) from tmp dir into organized music library.
        organized_files: List[str] = []
        for audio_path in downloaded:
            final_path = organize_audio_file(audio_path, user_music_dir)
            organized_files.append(final_path)

        # Ensure album-level tags are consistent for all tracks in each folder,
        # preventing media servers from splitting one album into multiple entries.
        force_album_consistency(organized_files)

        with jobs_lock:
            job.downloaded_files = organized_files
            job.logs.append("Organized files in user/artist/album structure")

        with jobs_lock:
            job.status = "done"
            job.finished_at = utc_now()

    except Exception as exc:
        with jobs_lock:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = utc_now()
            job.logs.append(f"ERROR: {exc}")

    finally:
        # Always clean up the per-job temp dir (thumbnails, intermediates, etc.).
        shutil.rmtree(job_tmp_dir, ignore_errors=True)


def worker_loop() -> None:
    while True:
        job_id = job_queue.get()
        try:
            process_job(job_id)
        finally:
            job_queue.task_done()


def render_home_page() -> str:
    with jobs_lock:
        jobs_list = list(jobs.values())

    rows = []
    for job in sorted(jobs_list, key=lambda j: j.created_at, reverse=True)[:20]:
        files = "<br>".join(job.downloaded_files[-5:]) if job.downloaded_files else "-"
        err = job.error or ""
        rows.append(
            f"<tr><td>{job.id}</td><td>{job.status}</td><td>{job.navidrome_user}</td>"
            f"<td>{job.output_format}</td><td>{job.created_at}</td><td>{files}</td><td>{err}</td></tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='7'>No jobs yet</td></tr>"

    return f"""
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>{APP_TITLE}</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: #f5f7fa; }}
    .card {{ background: white; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 4px 14px rgba(0,0,0,.06); }}
    input, select, button {{ width: 100%; padding: 10px; margin-top: 8px; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <div class='card'>
    <h2>GetMusic Downloader</h2>
    <form method='post' action='/download'>
      <label>YouTube Music URL (single or album/playlist)</label>
      <input name='url' required placeholder='https://music.youtube.com/...'>

      <label>Navidrome User Folder</label>
      <input name='navidrome_user' placeholder='gio'>

      <label>Output Format</label>
      <select name='output_format'>
                <option value='m4a' selected>m4a (recommended)</option>
        <option value='mp3'>mp3</option>
      </select>

      <label><input type='checkbox' name='embed_lyrics' value='1' checked> Fetch and embed lyrics</label>
      <button type='submit'>Queue Download</button>
    </form>
    <p><strong>Note:</strong> Downloads are audio-only. MP3 gets synced+plain lyrics embedded when available. M4A gets plain embedded lyrics plus .lrc sidecar.</p>
  </div>

  <div class='card'>
    <h3>Recent Jobs</h3>
    <table>
      <thead><tr><th>ID</th><th>Status</th><th>User</th><th>Format</th><th>Created</th><th>Files (last 5)</th><th>Error</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</body>
</html>
"""


@app.on_event("startup")
def startup_worker() -> None:
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return render_home_page()


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        payload = {
            "id": job.id,
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "downloaded_files": job.downloaded_files,
            "logs": job.logs[-100:],
        }
    return JSONResponse(payload)


@app.post("/download")
def create_download(
    url: str = Form(...),
    navidrome_user: str = Form("shared"),
    output_format: str = Form("m4a"),
    embed_lyrics: Optional[str] = Form(None),
) -> JSONResponse:
    if output_format not in {"mp3", "m4a"}:
        raise HTTPException(status_code=400, detail="Invalid output_format")

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        url=url.strip(),
        navidrome_user=sanitize_segment(navidrome_user, "shared"),
        output_format=output_format,
        embed_lyrics=bool(embed_lyrics),
    )

    with jobs_lock:
        jobs[job_id] = job

    job_queue.put(job_id)
    return JSONResponse({"status": "queued", "job_id": job_id})
