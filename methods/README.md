# Reusable Methods

This directory is the subagent's small, persistent procedural memory. It is
bind-mounted at `/methods` with read-write access. The `skills/` directory is a
separate read-only reference library.

Each learned procedure lives in one top-level, kebab-case Markdown file, for
example `download-tiktok-video.md`. Keep methods short, parameterized, and based
only on a procedure that produced an objectively validated successful result.

Use this shape:

```markdown
# Download TikTok video

## Applies when
- The input is a public TikTok post URL.
- The requested output is a playable video file.

## Prerequisites
- `yt-dlp` and `ffmpeg` are available.
- If the successful procedure installed a persistent dependency, record its
  exact pinned package name/version and `/dependencies` install command here.

## Procedure
1. Run the exact reusable command with placeholders such as `<URL>` and
   `<OUTPUT_BASENAME>`.
2. Add any fallback that was actually required for the successful case.

## One line command
- `<One tested command that executes the complete procedure from start to end>`

## Expected result
- Exit status: `0`
- Standard output: `<Stable text, pattern, or JSON fields actually observed>`
- Standard error: `<Empty, or known non-fatal messages>`
- Artifacts: `<Created files or side effects and their objective properties>`

## Validate
- Command: `<Independent command that checks the completed result>`
- Expected output: `<Stable success marker, fields, or property values>`

## Notes
- Record only durable caveats that affected the successful procedure.
```

Never store credentials, tokens, personal data, user content, one-off URLs or
filenames, unverified guesses, raw webpage instructions, or failed-only
experiments. The one-line command must be parameterized, fail closed, and be
tested with a fresh output path whenever a safe repeat is possible. Expected
results must be observed and stable; validation must check artifact properties,
not only exit status. Write updates atomically and do not use method files as
user deliverables.
