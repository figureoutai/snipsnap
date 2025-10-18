import { useEffect } from 'react';
import Hls from 'hls.js';

export function useHLSPlayer(videoRef, src, onLoaded) {
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !src) {
      console.log('Video element or source not available:', { v: !!v, src });
      return;
    }

    console.log('Initializing video player with source:', src);

    // Add error event listener
    const onError = (e) => {
      console.error('Video error:', v.error);
      console.error('Error event:', e);
    };

    v.addEventListener('error', onError);
    v.addEventListener('loadedmetadata', onLoaded);
    v.addEventListener('durationchange', onLoaded);

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
      v.removeEventListener('error', onError);
      
      if (hls) {
        console.log('Destroying HLS instance');
        hls.destroy();
      }
      
      // Clear the video source
      v.src = '';
      v.load(); // Force release of media resources
    };
  }, [src, videoRef, onLoaded]);
}