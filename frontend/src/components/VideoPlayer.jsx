import React, { useEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { toSeconds, formatTime } from '../utils/time.js';
import "../styles/videoPlayer.css";

const VideoPlayer = forwardRef(({ src, ranges = [] }, ref) => {
  const videoRef = useRef(null);
  const barRef = useRef(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onLoaded = () => setDuration(Number.isFinite(v.duration) ? v.duration : 0);
    const onTime = () => setCurrentTime(v.currentTime || 0);

    v.addEventListener('loadedmetadata', onLoaded);
    v.addEventListener('durationchange', onLoaded);
    v.addEventListener('timeupdate', onTime);

    // In case metadata is already available
    if (v.readyState >= 1) onLoaded();

    return () => {
      v.removeEventListener('loadedmetadata', onLoaded);
      v.removeEventListener('durationchange', onLoaded);
      v.removeEventListener('timeupdate', onTime);
    };
  }, [src]);

  const normalized = useMemo(() => {
    return ranges
      .map((r) => {
        const start = Math.max(0, toSeconds(r.start));
        const end = Math.max(0, toSeconds(r.end));
        return start < end ? { start, end } : null;
      })
      .filter(Boolean);
  }, [ranges]);

  const segments = useMemo(() => {
    if (!duration || duration <= 0) return [];
    return normalized.map(({ start, end }) => {
      const left = (start / duration) * 100;
      const width = ((end - start) / duration) * 100;
      return { left, width };
    });
  }, [normalized, duration]);

  const progressPct = useMemo(() => {
    if (!duration) return 0;
    return Math.min(100, Math.max(0, (currentTime / duration) * 100));
  }, [currentTime, duration]);

  const onSeek = (e) => {
    if (!barRef.current || !videoRef.current || !duration) return;
    const rect = barRef.current.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const t = Math.max(0, Math.min(duration, ratio * duration));
    videoRef.current.currentTime = t;
  };

  // Function to seek to timestamp and play
  const seekAndPlay = (start, end) => {
    if (!videoRef.current) return;
    
    const startTime = toSeconds(start);
    const endTime = toSeconds(end);
    
    // Seek to start time
    videoRef.current.currentTime = startTime;
    
    // Play the video
    videoRef.current.play();
    
    // Set up listener to pause at end time
    const checkTime = () => {
      if (videoRef.current.currentTime >= endTime) {
        videoRef.current.pause();
        videoRef.current.removeEventListener('timeupdate', checkTime);
      }
    };
    
    videoRef.current.addEventListener('timeupdate', checkTime);
    
    // Cleanup listener if component unmounts or new seek is called
    return () => {
      if (videoRef.current) {
        videoRef.current.removeEventListener('timeupdate', checkTime);
      }
    };
  };

  // Expose seekAndPlay method to parent components
  useImperativeHandle(ref, () => ({
    seekAndPlay
  }), []);

  return (
    <div className="player-container">
      <video
        ref={videoRef}
        className="video-el"
        src={src}
        controls
        playsInline
      />

      <div className="bar-wrap">
        <div ref={barRef} className="highlight-bar" onClick={onSeek}>
          {segments.map((s, i) => (
            <div
              key={i}
              className="highlight-range"
              style={{ left: `${s.left}%`, width: `${s.width}%` }}
              title="Highlight"
            />
          ))}
          <div className="playhead" style={{ left: `${progressPct}%` }} />
        </div>
        <div className="time-row">
          <span>{formatTime(currentTime)}</span>
          <span>{duration ? formatTime(duration) : '--:--'}</span>
        </div>
      </div>
    </div>
  );
});

export default VideoPlayer;