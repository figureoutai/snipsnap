# Clip Highlights Frontend

A minimal React + Vite app that plays a video (local path or URL) and displays highlight ranges on a custom timeline.

## Quick Start

Prereqs: Node.js 18+ and npm.

1. `cd frontend`
2. `npm install`
3. Put a small test video at `frontend/public/media/sample.mp4` (or use any URL).
4. `npm run dev`
5. Open the app (Vite will open a browser window at http://localhost:5173).

In the app, set the video path (e.g., `/media/sample.mp4` or a full https URL) and set highlight ranges as JSON.

## Ranges Format

Accepts an array of `{ start, end }` pairs. Each value can be:

- A number of seconds (e.g., `70`), or
- A time string in `m:ss` or `h:mm:ss` (e.g., `"1:10"`, `"0:05"`, `"2:03:45"`).

Example:

```json
[
  { "start": "0:05", "end": "0:08" },
  { "start": "1:10", "end": "1:25" }
]
```

## Notes

- The native video controls remain enabled. The highlight bar below the video is clickable for seeking.
- To stream from CloudFront later, simply pass the CloudFront URL to the `src` prop of the `VideoPlayer` component (no code changes required).
- If you change the port or run behind a reverse proxy, update Vite server config in `vite.config.js` if needed.

