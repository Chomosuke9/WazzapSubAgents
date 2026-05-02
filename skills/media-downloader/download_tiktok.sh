#!/bin/bash
# download_tiktok.sh - Download TikTok videos using siputzx API
# Prioritizes HD quality, falls back to SD if HD unavailable.
#
# Usage:
#   bash download_tiktok.sh <tiktok_url> [output_file]
#
# Examples:
#   bash download_tiktok.sh "https://vt.tiktok.com/ZSjXNEnbC/"
#   bash download_tiktok.sh "https://vt.tiktok.com/ZSjXNEnbC/" ./my_video.mp4

set -euo pipefail

URL="$1"
OUTPUT="${2:-./tiktok_video.mp4}"

# --- Validate input ---
if [ -z "$URL" ]; then
    echo "Usage: $0 <tiktok_url> [output_file]"
    echo "Example: $0 https://vt.tiktok.com/ZSjXNEnbC/ ./video.mp4"
    exit 1
fi

# --- Check dependencies ---
for cmd in curl jq python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd is not installed. Install with: apt-get install $cmd"
        exit 1
    fi
done

# --- Encode the TikTok URL ---
ENCODED_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$URL', safe=''))")

# --- Call the TikTok download API ---
echo "Fetching TikTok video info..."
API_RESPONSE=$(curl -s -X GET "https://api.siputzx.my.id/api/d/tiktok?url=${ENCODED_URL}")

# --- Validate API response ---
STATUS=$(echo "$API_RESPONSE" | jq -r '.status')
if [ "$STATUS" != "true" ]; then
    echo "Error: API returned unsuccessful status"
    echo "$API_RESPONSE" | jq .
    exit 1
fi

# --- Print video metadata ---
TITLE=$(echo "$API_RESPONSE" | jq -r '.data.title')
AUTHOR=$(echo "$API_RESPONSE" | jq -r '.data.author')
TYPE=$(echo "$API_RESPONSE" | jq -r '.data.type')
echo "Title:  $TITLE"
echo "Author: $AUTHOR"
echo "Type:   $TYPE"

# --- Extract video URL (prioritize HD, fallback to SD) ---
VIDEO_URL=$(echo "$API_RESPONSE" | jq -r '.data.media[] | select(.quality == "HD") | .url' | head -1)

if [ -z "$VIDEO_URL" ]; then
    echo "No HD quality found, falling back to SD..."
    VIDEO_URL=$(echo "$API_RESPONSE" | jq -r '.data.media[] | select(.quality == "SD") | .url' | head -1)
fi

if [ -z "$VIDEO_URL" ]; then
    echo "Error: No video URL found in API response"
    exit 1
fi

# --- Download the video ---
echo "Downloading video to $OUTPUT..."
curl -L -o "$OUTPUT" "$VIDEO_URL"

# --- Verify the download ---
if [ ! -f "$OUTPUT" ]; then
    echo "Error: Failed to download video"
    exit 1
fi

FILESIZE=$(stat -c%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT" 2>/dev/null || echo "0")
if [ "$FILESIZE" -eq 0 ]; then
    echo "Error: Downloaded file is 0 bytes"
    rm -f "$OUTPUT"
    exit 1
fi

echo "Download complete: $OUTPUT ($FILESIZE bytes)"