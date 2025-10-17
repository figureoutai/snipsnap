import { useCallback, useRef } from "react";
import VideoPlayer from "../../components/VideoPlayer";
import Loader from "../../components/Loader";
import "../../styles/highlight.css";
import useFetchHighlights from "../../hooks/useFetchHighlights";
import { constructThumbnailURL, constructVideoURL } from "../../utils/assetURL";
import { formatTime } from "../../utils/time";



function Highlights() {

    const {data, loading, error} = useFetchHighlights();
    const videoPlayerRef = useRef(null);

       
    const handleHighlightClick = useCallback((item) => {
        if (videoPlayerRef.current) {
            videoPlayerRef.current.seekAndPlay(item.start_time, item.end_time);
        }
    }, []);

    if (data === null || loading) {
        return <Loader />;
    }

    return (
        <div className="highlights-container">
            <div className="main-content">
                <div className="video-container">
                    <VideoPlayer 
                        ref={videoPlayerRef}
                        src={constructVideoURL(data.streamId, data.streamURL.split("/").splice(-1))}
                        ranges={data.highlightsTimestamps.map((item) => {
                            return {start: item.start_time, end: item.end_time};
                        })} 
                    />
                </div>
            </div>

            <div className="sidebar">
                <div className="sidebar-header">
                    <h2 className="sidebar-title">Highlights</h2>
                </div>
                <div className="sidebar-list">
                    {data.highlightsTimestamps.map((item, index) => {

                        return (
                            <div className="sidebar-item" key={index} onClick={() => handleHighlightClick(item)}>
                                <div className="sidebar-item-thumbnail">
                                    <img src={constructThumbnailURL(item.thumbnail)} alt={`Highlight ${index + 1}`} style={{ width: '120px', height: '68px', objectFit: 'cover', borderRadius: '4px' }} />
                                </div>
                                <div className="sidebar-item-content">
                                    <div className="item-title">{item.title}</div>
                                    <div className="item-description">{item.caption}</div>
                                    <div className="item-meta">{`Start: ${formatTime(item.start_time)} End: ${formatTime(item.end_time)}`}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

export default Highlights;