import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import VideoPlayer from "../../components/VideoPlayer";
import "../../styles/highlight.css";


const mockHighlights = [
  { start: '0:05', end: '0:08' },
  { start: '1:10', end: '1:25' },
];

const mockSourceVideo = '../../../public/media/sample.mp4';

function Highlights() {
    const params = useParams();

    const [streamId, setStreamId] = useState(null);
    const [sourceVideo, setSourceVideo] = useState(mockSourceVideo);
    const [highlightTimestamps, setHighlightTimestamps] = useState(mockHighlights);


    useEffect(() => {
        if(params.streamId){
            setStreamId(params.streamId);
        }
    }, [params]);


    useEffect(() => {
        /**
         * TODO: Make fetch API call with stream Id to get the following data from backend:
         * 1. cloudfront video source URL
         * 2. highlights timestamps
         * 
         * Once the data is retrieved update the state using setSourceVideo an setHighlightTimestamps
         */
    }, [streamId]);

    const handleHighlightClick = useCallback((item) => {
        console.log('ITEM ', item);
        /**
         * TODO: Use the streamID and the timestamps to download the highlight video from the backend
         */
    }, [streamId]);

    return (
        <div class="highlights-container">
            <div class="main-content">                
                <div class="video-container">
                    <VideoPlayer src={sourceVideo} ranges={highlightTimestamps}/>
                </div>
            </div>

            <div class="sidebar">
                <div class="sidebar-header">
                    <h2 class="sidebar-title">Highlights</h2>
                </div>
                <div class="sidebar-list">
                    {highlightTimestamps.map((item, index) => {

                        return (
                            <div class="sidebar-item" key={index} onClick={() => handleHighlightClick(item)}>
                                <div class="item-title">{`Highlight ${index + 1}`}</div>
                                {/* <div class="item-description">Learn the basics of HTML, CSS, and JavaScript</div> */}
                                <div class="item-meta">{`Start: ${item.start} End: ${item.end}`}</div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

export default Highlights;