import { useCallback, useRef, useState } from "react";
import VideoPlayer from "../../components/VideoPlayer";
import Loader from "../../components/Loader";
import Header from "../../components/Header";
import useFetchHighlights from "../../hooks/useFetchHighlights";
import { constructThumbnailURL, constructVideoURL } from "../../utils/assetURL";
import { formatTime } from "../../utils/time";
import "../../styles/highlight.css";


function Highlights() {
    
    const [selectedCaption, setSelectedCaption] = useState();
    const { data, loading, error } = useFetchHighlights();
    const videoPlayerRef = useRef(null);


    const handleHighlightClick = useCallback((item) => {
        if (videoPlayerRef.current) {
            videoPlayerRef.current.seekAndPlay(item.start_time, item.end_time);
            setSelectedCaption(item.caption);
        }
    }, []);

    const handleSegmentChange = useCallback((index) => {
        if (index === -1) {
            setSelectedCaption(undefined);
        } else if (data?.highlightsTimestamps?.[index]) {
            setSelectedCaption(data.highlightsTimestamps[index].caption);
        }
    }, [data?.highlightsTimestamps]);
   

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
                                <VideoPlayer
                                    ref={videoPlayerRef}
                                    src={constructVideoURL(data.streamId, data.streamURL.split("/").splice(-1)[0])}
                                    ranges={data.highlightsTimestamps.map((item) => ({
                                        start: item.start_time,
                                        end: item.end_time
                                    }))}
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