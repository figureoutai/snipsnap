import React, { useEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import Hls from 'hls.js';
import { toSeconds, formatTime } from '../utils/time.js';
import "../styles/videoPlayer.css";

const VideoPlayer = forwardRef(({ src, ranges = [], onSegmentChange }, ref) => {
  const videoRef = useRef(null);
  const barRef = useRef(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(-1);

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !src) {
      console.log('Video element or source not available:', { v: !!v, src });
      return;
    }

    console.log('Initializing video player with source:', src);

    const onLoaded = () => {
      console.log('Video metadata loaded, duration:', v.duration);
      setDuration(Number.isFinite(v.duration) ? v.duration : 0);
    };
    
    const onTime = () => {
      const time = v.currentTime || 0;
      setCurrentTime(time);
      
      // Check if current time is within any segment
      const activeIndex = normalized.findIndex(
        segment => time >= segment.start && time <= segment.end
      );
      
      // Call onSegmentChange when the active segment changes
      if (activeIndex !== activeSegmentIndex) {
        setActiveSegmentIndex(activeIndex);
        if (onSegmentChange) {
          onSegmentChange(activeIndex);
        }
      }
    };

    // Add error event listener
    const onError = (e) => {
      console.error('Video error:', v.error);
      console.error('Error event:', e);
    };

    v.addEventListener('error', onError);
    v.addEventListener('loadedmetadata', onLoaded);
    v.addEventListener('durationchange', onLoaded);
    v.addEventListener('timeupdate', onTime);

    let hls = null;

    // Check if the source is an HLS stream
    if (src.endsWith('.m3u8')) {
      console.log('HLS stream detected');
      
      if (Hls.isSupported()) {
        console.log('HLS.js is supported by this browser');
        
        hls = new Hls({
          debug: true,  // Enable debug logs
          maxLoadingDelay: 4,
          maxBufferLength: 30,
          liveDurationInfinity: true
        });
        
        // Add HLS specific error handlers
        hls.on(Hls.Events.ERROR, (event, data) => {
          console.error('HLS error:', { event, data });
          if (data.fatal) {
            console.error('Fatal HLS error:', data.type);
          }
        });

        hls.on(Hls.Events.MANIFEST_LOADING, () => {
          console.log('HLS: Manifest loading...');
        });

        hls.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
          console.log('HLS: Manifest parsed, found ' + data.levels.length + ' quality level(s)');
          if (v.paused) {
            console.log('Attempting to play video...');
            v.play()
              .then(() => console.log('Playback started'))
              .catch(error => console.error('Playback failed:', error));
          }
        });

        console.log('Loading HLS source:', src);
        hls.loadSource(src);
        hls.attachMedia(v);

        hls.on(Hls.Events.ERROR, (event, data) => {
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                console.log('Network error, trying to recover...');
                hls.startLoad();
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                console.log('Media error, trying to recover...');
                hls.recoverMediaError();
                break;
              default:
                console.error('Fatal error:', data);
                hls.destroy();
                break;
            }
          }
        });
      } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
        // For Safari which has built-in HLS support
        v.src = src;
      }
    } else {
      // Regular video source
      v.src = src;
    }

    // In case metadata is already available
    if (v.readyState >= 1) onLoaded();

    return () => {
      v.removeEventListener('loadedmetadata', onLoaded);
      v.removeEventListener('durationchange', onLoaded);
      v.removeEventListener('timeupdate', onTime);
      v.removeEventListener('error', onError);
      
      if (hls) {
        console.log('Destroying HLS instance');
        hls.destroy();
      }
      
      // Clear the video source
      v.src = '';
      v.load(); // Force release of media resources
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
        controls
        playsInline
      />

      <div className="bar-wrap">
        <div ref={barRef} className="highlight-bar" onClick={onSeek}>
          {segments.map((s, i) => (
            <div
              key={i}
              className={`highlight-range ${i === activeSegmentIndex ? 'active' : ''}`}
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