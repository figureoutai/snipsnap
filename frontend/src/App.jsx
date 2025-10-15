import React, { useState } from 'react';
import VideoPlayer from './components/VideoPlayer.jsx';
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import Dashboard from './pages/dashboard/index.jsx';
import Highlights from './pages/highlights/index.jsx';


const router = createBrowserRouter([
  {
    path: '/',
    element: <Dashboard/>
  },
  {
    path: 'highlights/:streamId',
    element: <Highlights/>
  }
]);

function App(){

  return <RouterProvider router={router}/>
}

export default App;

// const defaultRanges = [
//   { start: '0:05', end: '0:08' },
//   { start: '1:10', end: '1:25' },
// ];

// export default function App() {
//   const [src, setSrc] = useState('/media/sample.mp4');
//   const [ranges, setRanges] = useState(defaultRanges);

//   return (
//     <div className="app-shell">
//       <h1>Clip Highlights Player</h1>

//       <section className="controls">
//         <label className="field">
//           <span>Video path or URL</span>
//           <input
//             type="text"
//             value={src}
//             onChange={(e) => setSrc(e.target.value)}
//             placeholder="/media/sample.mp4 or https://..."
//           />
//         </label>

//         <label className="field">
//           <span>Highlight ranges (JSON)</span>
//           <textarea
//             rows={4}
//             value={JSON.stringify(ranges)}
//             onChange={(e) => {
//               try {
//                 const next = JSON.parse(e.target.value);
//                 if (Array.isArray(next)) setRanges(next);
//               } catch (_) {
//                 /* ignore until valid JSON */
//               }
//             }}
//           />
//         </label>
//       </section>

//       <VideoPlayer src={src} ranges={ranges} />

//       <p className="hint">
//         Tip: Put a small video at <code>frontend/public/media/sample.mp4</code> or paste a
//         full URL. Ranges accept <code>m:ss</code> or <code>h:mm:ss</code> strings.
//       </p>
//     </div>
//   );
// }
