import React, { useEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle, useCallback } from 'react';
import { toSeconds, formatTime } from '../utils/time.js';
import { useHLSPlayer } from '../hooks/useHLSPlayer';
import "../styles/videoPlayer.css";

const VideoPlayer = forwardRef(({ src, ranges = [], onSegmentChange }, ref) => {
  const videoRef = useRef(null);
  const barRef = useRef(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(-1);

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

  // Function to find active segment index
  const handleSegmentChange = useCallback((newIndex) => {
    setActiveSegmentIndex(newIndex);
    if (onSegmentChange) {
      onSegmentChange(newIndex);
    }
  }, [onSegmentChange]);

  const findActiveSegment = useCallback((startTime) => {
    return normalized.findLastIndex((segment) => (startTime >= segment.start) && (startTime < segment.end));
  }, [normalized]);

  const updateActiveSegmentForTime = useCallback((time) => {
    const activeIndex = findActiveSegment(time);

    if (activeIndex !== activeSegmentIndex) {
      handleSegmentChange(activeIndex);
    }
  }, [activeSegmentIndex, handleSegmentChange, findActiveSegment]);

  // Function to seek to timestamp and play
  const seekAndPlay = useCallback((start, end) => {
    if (!videoRef.current) return;

    const startTime = toSeconds(start);
    const endTime = toSeconds(end);

    // Then seek to start time and pause
    videoRef.current.currentTime = startTime;
    videoRef.current.pause();

    // Set up listener to pause at end time (in case video is played later)
    const checkTime = () => {
      if (videoRef.current.currentTime >= endTime) {
        videoRef.current.pause();
        videoRef.current.removeEventListener('timeupdate', checkTime);
      }
    };

    videoRef.current.addEventListener('timeupdate', checkTime);
  }, []);

  // Expose seekAndPlay method to parent components
  useImperativeHandle(ref, () => ({
    seekAndPlay
  }), [seekAndPlay]);

  const onLoaded = useCallback(() => {
    if (!videoRef.current) return;
    console.log('Video metadata loaded, duration:', videoRef.current.duration);
    setDuration(Number.isFinite(videoRef.current.duration) ? videoRef.current.duration : 0);
  }, []);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTime = () => {
      const time = v.currentTime || 0;
      setCurrentTime(time);
      updateActiveSegmentForTime(time);
    };

    v.addEventListener('timeupdate', onTime);

    return () => {
      v.removeEventListener('timeupdate', onTime);
    };
  }, [normalized, activeSegmentIndex, handleSegmentChange]);

  // Use the HLS player hook
  useHLSPlayer(videoRef, src, onLoaded);

  const onSeek = useCallback((e) => {
    if (!barRef.current || !videoRef.current || !duration) return;
    const rect = barRef.current.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const t = Math.max(0, Math.min(duration, ratio * duration));
    videoRef.current.currentTime = t;
  }, [duration]);


  return (
    <div className="player-container">
      <video
        ref={videoRef}
        className="video-el"
        controls
        playsInline
        autoPlay
      />

      <div className="bar-wrap">
        <div ref={barRef} className="highlight-bar" onClick={onSeek}>
          {segments.map((s, i) => (
            <div key={i} style={{ display: 'inline-block', position: 'absolute', top: 0, height: '100%', left: `${s.left}%`, width: `${s.width}%`, background: 'blue' }}>
              {(i === activeSegmentIndex) && <div style={{ position: 'relative', width: '1%', height: '30px', top: '-10px', background: 'white', zIndex: 999 }} />}
              <div key={i} className={`highlight-range ${i === activeSegmentIndex ? 'active' : ''}`} style={{ width: '100%' }} title="Highlight" />
              {(i === activeSegmentIndex) && <div style={{ position: 'relative', left: '100%', width: '1%', height: '30px', top: '-40px', background: 'white', zIndex: 999 }} />}
            </div>
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