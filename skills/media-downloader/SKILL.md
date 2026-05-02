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

- **yt-dlp** — video/audio from YouTube, TikTok, Instagram, Twitter/X, Facebook, 1000+ sites
- **spotdl** — Spotify tracks/playlists/albums with metadata, art, lyrics

Output files go into the **current working directory** — use relative paths like `./video.mp4`.

---

## Quick Decision Tree

```
URL provided?
├── spotify.com                       → spotdl download <url>
├── youtube/tiktok/instagram/twitter  → yt-dlp <url>
└── any other site                    → yt-dlp <url>

No URL?
├── Spotify song  → spotdl download "song artist"
└── YouTube video → yt-dlp "ytsearch1:title"
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Best quality video | `yt-dlp <url>` |
| Force MP4 | `yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" -o "./video.mp4" <url>` |
| Audio only (MP3) | `yt-dlp -x --audio-format mp3 -o "./audio.%(ext)s" <url>` |
| Audio only (M4A) | `yt-dlp -f "ba" -x --audio-format m4a -o "./audio.%(ext)s" <url>` |
| Max resolution | `yt-dlp -f "bv*[height<=720]+ba/b" <url>` |
| List formats | `yt-dlp -F <url>` |
| Playlist | `yt-dlp -o "./%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s" <url>` |
| With subtitles | `yt-dlp --write-subs --write-auto-subs --sub-langs en <url>` |
| Embed metadata | `yt-dlp --embed-thumbnail --embed-metadata <url>` |
| Spotify track | `spotdl download <url>` |
| Spotify playlist/album | `spotdl download <url>` |
| Spotify search | `spotdl download "Bohemian Rhapsody Queen"` |
| Spotify as FLAC | `spotdl download <url> --format flac` |
| Spotify output dir | `spotdl download <url> --output "./downloads"` |

---

## Error Handling

| Error | Fix |
|-------|-----|
| `Video unavailable` / geo-blocked | Use `--proxy` or inform user |
| `Sign in to confirm your age` | `--cookies-from-browser chrome` |
| `HTTP 429 Too Many Requests` | Add `--sleep-requests 1 --sleep-interval 5` |
| `ffmpeg not found` | `apt-get install ffmpeg` |
| TikTok fails | `pip install --upgrade yt-dlp` |
| 0-byte file | `yt-dlp --no-cache-dir <url>` |
| spotdl wrong match | `spotdl download "artist - track name"` |
| Private Spotify playlist | Ask user to make it public |

---

## Notes

- Always verify output: `ls -la` or `os.path.getsize()` — never report success on 0-byte files.
- spotdl sources audio from YouTube (not Spotify directly); quality capped at ~256 kbps.
- For batch downloads, use `--sleep-requests 1 --sleep-interval 5` to avoid IP bans.
- `--restrict-filenames` on yt-dlp replaces special chars for cross-platform safety.
