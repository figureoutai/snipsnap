import { useCallback, useRef, useState, useMemo, memo } from "react";
import VideoPlayer from "../../components/VideoPlayer";
import Loader from "../../components/Loader";
import Header from "../../components/Header";
import useFetchHighlights from "../../hooks/useFetchHighlights";
import { constructThumbnailURL, constructVideoURL } from "../../utils/assetURL";
import { formatTime } from "../../utils/time";
import "../../styles/highlight.css";


const MemoizedVideoPlayer = memo(VideoPlayer);

function Highlights() {
    
    const [selectedCaption, setSelectedCaption] = useState();
    const { data, loading, error } = useFetchHighlights();
    const videoPlayerRef = useRef(null);


    const handleHighlightClick = useCallback((item) => {
        if (videoPlayerRef.current) {
            videoPlayerRef.current.seekAndPlay(item.start_time, item.end_time);
        }
    }, []);

    // Memoize highlights data to prevent unnecessary re-renders
    const highlightsData = useMemo(() => data?.highlightsTimestamps || [], [data?.highlightsTimestamps]);

    // Memoize the ranges prop to prevent recreation
    const videoRanges = useMemo(() => 
        highlightsData.map((item) => ({
            start: item.start_time,
            end: item.end_time
        })),
        [highlightsData]
    );

    const handleSegmentChange = useCallback((index) => {
        if (index === -1) {
            setSelectedCaption(undefined);
        } else if (highlightsData[index]) {
            setSelectedCaption(highlightsData[index].caption);
        }
    }, [highlightsData]);
    
    const sourceVideoURL = useMemo(() => {
        if(!data)
            return '';
        if(!data.streamId || !data.streamURL)
            return '';
        
        return constructVideoURL(data.streamId, data.streamURL.split("/").splice(-1)[0]);
    }, [data]);

    return (
        <div className="highlights-container">
            <Header />            
            <div className="content-wrapper">
                {loading || (data === null) ? (
                    <div className="main-section">
                        <div className="loader-container">
                            <Loader message="Loading highlights..." />
                        </div>
                    </div>
                ) : error ? (
                    <div className="main-section">
                        <div className="error-container">
                            <div className="error-message">
                                {`Error loading highlights: ${error}`}
                            </div>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="main-content">
                            <div className="video-container">
                                {/* <VideoPlayer
                                    ref={videoPlayerRef}
                                    src={constructVideoURL(data.streamId, data.streamURL.split("/").splice(-1)[0])}
                                    ranges={videoRanges}
                                    onSegmentChange={handleSegmentChange}
                                /> */}
                                <MemoizedVideoPlayer
                                    ref={videoPlayerRef}
                                    src={sourceVideoURL}
                                    ranges={videoRanges}
                                    onSegmentChange={handleSegmentChange}
                                />
                            </div>
                            {selectedCaption && (
                                <div className="caption-container">
                                    {selectedCaption}
                                </div>
                            )}
                        </div>

                        <div className="sidebar">
                            <div className="sidebar-header">
                                <h2 className="sidebar-title">Highlights</h2>
                            </div>
                            <div className="sidebar-list">
                                {data.highlightsTimestamps.map((item, index) => (
                                    <div 
                                        className="sidebar-item" 
                                        key={index} 
                                        onClick={() => handleHighlightClick(item)}
                                    >
                                        <div className="sidebar-item-thumbnail">
                                            <img 
                                                src={constructThumbnailURL(data.streamId, item.thumbnail)} 
                                                alt={`Highlight ${index + 1}`} 
                                                style={{ 
                                                    width: '120px', 
                                                    height: '68px', 
                                                    objectFit: 'cover', 
                                                    borderRadius: '4px' 
                                                }} 
                                            />
                                        </div>
                                        <div className="sidebar-item-content">
                                            <div className="item-title">{item.title}</div>
                                            <div className="item-description">{item.caption}</div>
                                            <div className="item-meta">
                                                {`Start: ${formatTime(item.start_time)} End: ${formatTime(item.end_time)}`}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

export default Highlights;