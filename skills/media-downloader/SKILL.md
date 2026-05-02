---
name: media-downloader-agent
description: |
  Download videos from YouTube, TikTok, Instagram, Twitter/X, Facebook,
  and 1000+ other sites using yt-dlp. Download Spotify tracks, playlists,
  and albums with metadata, album art, and lyrics using spotdl.
  Use this skill whenever the user asks to download, save, or rip media
  from the internet — videos, audio, music, or playlists.
---

# Media Downloader Agent

Sub-agent skill for downloading media from the internet. Handles two
domains:

- **Video/Audio downloads** — YouTube, TikTok, Instagram, Twitter/X,
  Facebook, and 1000+ other sites via `yt-dlp`.
- **Spotify music downloads** — tracks, playlists, and albums with full
  metadata, album art, and lyrics via `spotdl`.

Output files go into the **current working directory (workdir)** — use
relative paths like `./video.mp4`. Never hard-code `/output/` or any
other absolute path.

---

## Quick Decision Tree

```
User provides a URL?
├── spotify.com URL → spotdl
│   ├── Track URL   → spotdl download <url>
│   ├── Playlist URL → spotdl download <url>
│   └── Album URL   → spotdl download <url>
├── youtube.com /youtu.be URL → yt-dlp
│   ├── Video only  → yt-dlp <url>
│   └── Audio only  → yt-dlp -x --audio-format mp3 <url>
├── tiktok.com URL → yt-dlp <url>
├── instagram.com URL → yt-dlp <url>
├── twitter.com /x.com URL → yt-dlp <url>
├── facebook.com URL → yt-dlp <url>
└── Any other URL → yt-dlp (supports 1000+ sites)

User describes media without URL?
├── "Download <song> by <artist> from Spotify" → spotdl search "<song> <artist>"
├── "Download <video> from YouTube" → yt-dlp "ytsearch:<video name>"
└── "Download music/mp3" → ask for URL or use yt-dlp search
```

---

## Quick Reference

| Task                              | Tool      | Command Snippet |
|-----------------------------------|-----------|-----------------|
| Download video (best quality)     | `yt-dlp`  | `yt-dlp <url>` |
| Download video as MP4             | `yt-dlp`  | `yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" <url>` |
| Download audio only (MP3)         | `yt-dlp`  | `yt-dlp -x --audio-format mp3 <url>` |
| Download audio only (M4A)         | `yt-dlp`  | `yt-dlp -f "ba[ext=m4a]/ba" -x <url>` |
| Download playlist                 | `yt-dlp`  | `yt-dlp <playlist_url>` |
| Download with custom filename     | `yt-dlp`  | `yt-dlp -o "./my_video.%(ext)s" <url>` |
| Download with subtitles           | `yt-dlp`  | `yt-dlp --write-subs --sub-langs en <url>` |
| Download Spotify track            | `spotdl`  | `spotdl download <url>` |
| Download Spotify playlist         | `spotdl`  | `spotdl download <url>` |
| Download Spotify album            | `spotdl`  | `spotdl download <url>` |
| Search & download Spotify song    | `spotdl`  | `spotdl download "song name artist"` |
| Download Spotify as MP3           | `spotdl`  | `spotdl download <url> --format mp3` |
| Download Spotify as FLAC          | `spotdl`  | `spotdl download <url> --format flac` |
| Preview available formats         | `yt-dlp`  | `yt-dlp -F <url>` |

---

## 1. yt-dlp — Video & Audio Downloads

`yt-dlp` is a command-line tool that downloads video/audio from YouTube
and 1000+ other sites. It requires **ffmpeg** (pre-installed) for
merging video+audio streams and for audio transcoding.

### 1.1 Basic video download

Downloads the best quality video+audio combined as a single file:

```bash
yt-dlp "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

The default output filename is `<title>.<ext>`. Use `-o` to customize.

### 1.2 Download video as MP4

Force MP4 container (most compatible format):

```bash
yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" \
  -o "./video.mp4" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 1.3 Download audio only (MP3)

Extract audio and convert to MP3:

```bash
yt-dlp -x --audio-format mp3 \
  -o "./audio.%(ext)s" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

The `-x` flag extracts audio; `--audio-format mp3` transcodes to MP3.
Supported audio formats: `mp3`, `m4a`, `opus`, `vorbis`, `wav`, `flac`.

### 1.4 Download audio only (best quality, M4A/Opus)

Download the best audio stream without re-encoding when possible:

```bash
yt-dlp -f "ba" -x --audio-format m4a \
  -o "./audio.%(ext)s" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 1.5 Download playlist

Downloads all videos in a YouTube playlist:

```bash
yt-dlp -o "./%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s" \
  "https://www.youtube.com/playlist?list=PLxxxxxxxxxx"
```

Useful playlist output template fields:
- `%(playlist_title)s` — playlist name
- `%(playlist_index)03d` — zero-padded index (001, 002, …)
- `%(title)s` — video title
- `%(ext)s` — file extension

To limit the number of videos downloaded from a playlist:

```bash
yt-dlp --playlist-end 10 <playlist_url>   # first 10 videos
yt-dlp --playlist-start 5 <playlist_url>  # start from video 5
```

### 1.6 Download with subtitles

```bash
# Download with English subtitles (auto-generated if manual not available)
yt-dlp --write-subs --write-auto-subs --sub-langs en \
  -o "./video.%(ext)s" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Burn subtitles into the video
yt-dlp --write-subs --sub-langs en --embed-subs \
  -o "./video.%(ext)s" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### 1.7 Download thumbnail

```bash
yt-dlp --write-thumbnail -o "./thumbnail.%(ext)s" <url>
```

### 1.8 Download from TikTok

```bash
yt-dlp "https://www.tiktok.com/@user/video/1234567890"
```

TikTok may require specific handling. If downloads fail, try:

```bash
yt-dlp -- extractor-descriptions "TikTok" <url>
yt-dlp --cookies-from-browser chrome <url>   # if login required
```

### 1.9 Download from Instagram

```bash
# Public post
yt-dlp "https://www.instagram.com/p/ABC123/"

# Reel
yt-dlp "https://www.instagram.com/reel/ABC123/"

# Stories (requires login — use cookies)
yt-dlp --cookies-from-browser chrome "https://www.instagram.com/stories/user/12345/"
```

### 1.10 Download from Twitter/X

```bash
yt-dlp "https://twitter.com/user/status/1234567890"
yt-dlp "https://x.com/user/status/1234567890"
```

### 1.11 Search YouTube and download

```bash
yt-dlp "ytsearch:Coldplay Yellow official video"
```

Use `ytsearch<N>:` to limit the number of search results:

```bash
yt-dlp "ytsearch1:Never Gonna Give You Up Rick Astley"
```

### 1.12 Format selection

List all available formats for a video:

```bash
yt-dlp -F "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Sample output:
```
ID  EXT   RESOLUTION FPS CH │  FILESIZE   TBR PROTO │ VCODEC        VBR ACODEC      ABR
──────────────────────────────────────────────────────────────────────────────────────────
140 m4a   audio only      2 │   3.27MiB   129k https │ audio only        mp4a.40.2   129k
251 webm  audio only      2 │   3.27MiB   129k https │ audio only        opus        129k
136 mp4   720p    30    2 │  10.00MiB   500k https │ avc1.4d401f   500k video only
137 mp4   1080p   30    2 │  20.00MiB  1000k https │ avc1.640028  1000k video only
```

Then download a specific format by ID:

```bash
yt-dlp -f 137+140 -o "./video.mp4" <url>
```

### 1.13 Output filename template

The `-o` flag accepts Python `strftime`-like format strings:

```bash
# Clean title, no special characters
yt-dlp -o "./%(title)s.%(ext)s" <url>

# Custom structure
yt-dlp -o "./downloads/%(uploader)s/%(upload_date)s - %(title)s.%(ext)s" <url>

# Restrict filenames to ASCII (replace special chars)
yt-dlp --restrict-filenames -o "./video.%(ext)s" <url>
```

Common template fields:
| Field | Description |
|-------|-------------|
| `%(title)s` | Video title |
| `%(ext)s` | File extension |
| `%(uploader)s` | Uploader name |
| `%(upload_date)s` | Upload date (YYYYMMDD) |
| `%(duration)s` | Duration in seconds |
| `%(id)s` | Video ID |
| `%(playlist_title)s` | Playlist title |
| `%(playlist_index)s` | Index in playlist |

### 1.14 Rate limiting

Avoid getting rate-limited or IP-banned:

```bash
# Limit download speed to 1MB/s
yt-dlp --limit-rate 1M <url>

# Sleep between downloads (for playlists)
yt-dlp --sleep-requests 1 --sleep-interval 5 <url>
```

### 1.15 Embed metadata and thumbnail

```bash
yt-dlp --embed-thumbnail --embed-metadata \
  -o "./video.%(ext)s" <url>
```

Note: `--embed-thumbnail` works with MP4/M4A containers. It does **not**
work with MKV or WebM output by default.

---

## 2. spotdl — Spotify Music Downloads

`spotdl` finds songs from Spotify on YouTube, downloads the audio, and
embeds Spotify metadata (title, artist, album, album art, lyrics).

### 2.1 Download a single track

```bash
spotdl download "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
```

This downloads the song and saves it as `<artist> - <title>.mp3` (by
default).

### 2.2 Download a playlist

```bash
spotdl download "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
```

All songs in the playlist will be downloaded to the current directory.

### 2.3 Download an album

```bash
spotdl download "https://open.spotify.com/album/1DFrjAk0QLfsY3EN7UJM2h"
```

### 2.4 Search and download by name

If the user provides a song name without a URL:

```bash
spotdl download "Bohemian Rhapsody Queen"
```

spotdl will search Spotify for the song, find it on YouTube, and
download it.

### 2.5 Output format selection

spotdl supports several audio formats:

```bash
# MP3 (default)
spotdl download <url> --format mp3

# FLAC (lossless)
spotdl download <url> --format flac

# Opus
spotdl download <url> --format opus

# M4A
spotdl download <url> --format m4a

# WAV
spotdl download <url> --format wav
```

### 2.6 Custom output directory and filename

```bash
spotdl download <url> --output "./downloads"
```

The `--output` flag sets the output directory. spotdl will create the
directory if it doesn't exist.

### 2.7 Sync a playlist directory

The `sync` operation keeps a local directory in sync with a Spotify
playlist. New songs are downloaded, and removed songs are deleted:

```bash
# First sync: creates a .spotdl file tracking the playlist state
spotdl sync "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" \
  --save-file ./playlist.spotdl

# Subsequent syncs: only downloads new songs, deletes removed ones
spotdl sync ./playlist.spotdl
```

### 2.8 Pre-fetch metadata without downloading

```bash
spotdl save "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" \
  --save-file ./playlist.spotdl
```

This saves a `.spotdl` file with song metadata. Useful for previewing
what will be downloaded.

### 2.9 Get YouTube URL for a Spotify track

```bash
spotdl url "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
```

Prints the matched YouTube URL without downloading anything.

---

## 3. Python Integration

For more complex workflows, both tools can be called from Python via
`subprocess`:

### 3.1 yt-dlp from Python

```python
import subprocess
import os

def download_video(url, output_dir=".", format="best", audio_only=False):
    """Download video or audio from a URL using yt-dlp."""
    cmd = ["yt-dlp"]

    if audio_only:
        cmd += ["-x", "--audio-format", format if format != "best" else "mp3"]
    elif format != "best":
        cmd += ["-f", format]

    cmd += ["-o", os.path.join(output_dir, "%(title)s.%(ext)s"), url]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Download successful: {url}")
        print(result.stdout)
    else:
        print(f"Download failed: {result.stderr}")
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    return result

# Example: download best quality video
download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

# Example: download audio only as MP3
download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", audio_only=True)
```

### 3.2 spotdl from Python

```python
import subprocess
import os

def download_spotify(url, output_dir=".", format="mp3"):
    """Download a Spotify track, playlist, or album using spotdl."""
    cmd = ["spotdl", "download", url, "--format", format, "--output", output_dir]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Download successful: {url}")
        print(result.stdout)
    else:
        print(f"Download failed: {result.stderr}")
        raise RuntimeError(f"spotdl failed: {result.stderr}")

    return result

# Example: download a track
download_spotify("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")

# Example: download a playlist as FLAC
download_spotify("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
                 format="flac")
```

### 3.3 Verify downloaded files

Always check that files exist and are not empty before reporting success:

```python
import os
import glob

def verify_downloads(output_dir=".", expected_ext=None):
    """Verify that downloaded files exist and are not empty."""
    pattern = os.path.join(output_dir, "**/*." + expected_ext) if expected_ext \
              else os.path.join(output_dir, "**/*")
    files = glob.glob(pattern, recursive=True)

    if not files:
        raise FileNotFoundError("No downloaded files found!")

    for f in files:
        size = os.path.getsize(f)
        if size == 0:
            print(f"WARNING: {f} is empty (0 bytes)")
        else:
            print(f"OK: {f} ({size:,} bytes)")

    return files

# Example: verify MP3 files
verify_downloads("./", expected_ext="mp3")
```

---

## 4. Advanced Patterns

### 4.1 Download multiple URLs

```bash
# yt-dlp accepts multiple URLs
yt-dlp -o "./%(title)s.%(ext)s" \
  "https://www.youtube.com/watch?v=VIDEO1" \
  "https://www.youtube.com/watch?v=VIDEO2"

# spotdl accepts multiple URLs
spotdl download \
  "https://open.spotify.com/track/TRACK1" \
  "https://open.spotify.com/track/TRACK2"
```

### 4.2 Batch download from file

```bash
# Create a file with one URL per line
yt-dlp -a ./urls.txt -o "./%(title)s.%(ext)s"
```

### 4.3 Download age-restricted or private content

Some content requires authentication. Use browser cookies:

```bash
# Export cookies from Chrome (requires cookies in browser)
yt-dlp --cookies-from-browser chrome <url>

# Export cookies from Firefox
yt-dlp --cookies-from-browser firefox <url>

# Use a cookies.txt file (NetScape format)
yt-dlp --cookies ./cookies.txt <url>
```

Note: `--cookies-from-browser` may not work in a container environment
without a browser installed. In that case, use a `cookies.txt` file
exported from a browser extension.

### 4.4 Proxy support

```bash
yt-dlp --proxy "socks5://127.0.0.1:1080" <url>
```

### 4.5 Download specific resolution

```bash
# 720p max
yt-dlp -f "bv*[height<=720]+ba/b[height<=720]/b" <url>

# 480p max (smaller file size)
yt-dlp -f "bv*[height<=480]+ba/b[height<=480]/b" <url>

# 4K
yt-dlp -f "bv*[height>=2160]+ba/b[height>=2160]/b" <url>
```

### 4.6 Download live stream after it ends

```bash
# Wait for a live stream to finish, then download
yt-dlp --wait-for-video 60 <url>
```

---

## 5. Error Handling Checklist

| Scenario | Error / Symptom | Fix |
|----------|-----------------|-----|
| Video unavailable / geo-restricted | `Video unavailable` or `ERROR: Sign in to confirm your age` | Try `--cookies-from-browser` or `--proxy`. Inform user the content may be geo-blocked. |
| Age-restricted content | `Sign in to confirm your age` | Requires cookies: `--cookies-from-browser chrome` or `--cookies cookies.txt` |
| Rate-limited by YouTube | `HTTP Error 429: Too Many Requests` | Add `--sleep-requests 1 --sleep-interval 5` between downloads. Reduce concurrency. |
| ffmpeg not found | `ERROR: ffprobe/ffmpeg not found` | ffmpeg should be pre-installed. If missing: `apt-get install ffmpeg`. |
| spotdl can't find song on YouTube | `Unable to find a match on YouTube` | Try providing a more specific search query, or use `spotdl download "artist - song title"`. |
| SpotDL metadata mismatch | Wrong song downloaded | spotdl matches Spotify tracks to YouTube videos automatically; mismatches can occur. Try `spotdl download "artist - track name"` for manual search. |
| Private Spotify playlist | `Spotify playlist not found` | The playlist must be public or the tracks must be accessible. Ask user to make it public. |
| TikTok download fails | `ERROR: Unable to download` | TikTok frequently changes their API. Ensure `yt-dlp` is up to date: `pip install --upgrade yt-dlp`. |
| Instagram login required | `Login required` | Use `--cookies-from-browser` or `--cookies cookies.txt`. |
| Corrupted download / 0 bytes | File exists but is 0 bytes | Re-download with `yt-dlp --no-cache-dir <url>`. Verify with `ls -la`. |
| Playlist partially downloaded | Some videos skipped | Check `yt-dlp` output for per-video errors. Re-run for failed items. |
| Audio quality not as expected | Low bitrate MP3 | yt-dlp defaults to best quality. For higher quality, specify `--audio-quality 0` (0 = best, 10 = worst). |
| Merged video has no audio | `Requested format is not available` | Ensure ffmpeg is installed. Use `-f "bv*+ba/b"` to explicitly select best video + best audio. |

---

## 6. Best Practices for Sub-Agent

1. **Always verify downloads** — After downloading, check that the file
   exists and is not empty (0 bytes). Use `ls -la` or Python's
   `os.path.getsize()` to confirm.

2. **Use `-o` or `--output`** — Always specify an explicit output path to
   avoid files being saved to unexpected locations. Use relative paths
   like `./video.mp4`.

3. **Use `--restrict-filenames`** for yt-dlp when cross-platform
   compatibility matters. This replaces special characters in filenames.

4. **Prefer MP4 for video, MP3/M4A for audio** — These are the most
   universally compatible formats.

5. **Handle playlists carefully** — Playlist downloads create many files.
   Use a subdirectory: `yt-dlp -o "./playlist/%(title)s.%(ext)s" <url>`.

6. **Rate-limit batch downloads** — Use `--sleep-requests` and
   `--sleep-interval` when downloading many files to avoid IP bans.

7. **SpotDL downloads from YouTube, not Spotify directly** — spotdl finds
   the Spotify song on YouTube, downloads the audio, and then tags it
   with Spotify metadata. Audio quality is limited to YouTube's max
   (128 kbps for free users, 256 kbps for YouTube Music premium).

8. **Declare only deliverables** — List only the final media files in
   `end_task(output_files=[...])`. Skip scratch files, `.spotdl` tracking
   files, or partial downloads.

9. **Large files** — For very large video downloads, consider using
   `--limit-rate` to avoid consuming all available bandwidth, and inform
   the user that the download may take time.

10. **Metadata embedding** — Use `--embed-metadata` (yt-dlp) and spotdl's
    default behavior to ensure downloaded files have proper tags, album
    art, and title information.