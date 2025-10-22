# Clip Highlights Frontend

React + Vite UI for submitting video URLs and viewing highlight ranges with an HLS player and custom timeline.

## Quick Start

- Prereqs: Node.js 18+ and npm.

1. `cd frontend`
2. `npm install`
3. Create `.env.local` with API and asset endpoints:
   ```env
   VITE_APP_NAME="SnipSnap"
   VITE_API_BASE_URL=http://localhost:3000
   # When deployed, use CloudFront: https://<domain>/streams/
   VITE_ASSET_BASE_URL=http://localhost:3000/streams/
   ```
4. `npm run dev` and open http://localhost:5173 if it doesn’t open automatically.

## Build & Preview

- Production build: `npm run build` (outputs to `dist/`)
- Local preview of the production build: `npm run preview`