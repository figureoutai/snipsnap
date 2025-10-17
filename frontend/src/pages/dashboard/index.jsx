import React, { useCallback, useState } from 'react';
import { useNavigate } from 'react-router';
import useFetchStreams from '../../hooks/useFetchStreams';
import useSubmitVideo from '../../hooks/useSubmitVideo';
import Loader from '../../components/Loader';
import Header from '../../components/Header';
import '../../styles/dashboard.css';
import { constructThumbnailURL } from '../../utils/assetURL';

function Dashboard() {
    const navigate = useNavigate();
    const [searchQuery, setSearchQuery] = useState('');
    const { submitVideo, loading: submitting, error: submitError } = useSubmitVideo();
    
    // Initialize with 12 items per page for a 3x4 grid
    const { 
        data, 
        loading, 
        error, 
        page, 
        goToPage, 
        setItemsPerPage,
        refetch 
    } = useFetchStreams(1, 12);

    const handleTileClick = useCallback((stream) => {
        navigate(`/highlights/${stream.stream_id}`);
    }, [navigate]);

    const handleGenerate = useCallback(async () => {
        if (!searchQuery.trim()) {
            return;
        }

        try {
            await submitVideo(searchQuery.trim());
            setSearchQuery(''); // Clear input after successful submission
            await refetch(); // Refresh the streams list
        } catch (err) {
            console.error('Failed to submit video:', err);
        }
    }, [searchQuery, submitVideo, refetch]);


    return (
        <div className='dashboard-container'>
            <Header />
            <div className="search-section">
                <div className="search-container">
                    <div className="search-wrapper">
                        <input 
                            type="text" 
                            className="search-bar" 
                            placeholder="Enter video URL" 
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                        <button 
                            className="generate-btn" 
                            onClick={handleGenerate}
                            disabled={submitting || !searchQuery.trim()}
                        >
                            {submitting ? 'Submitting...' : 'Generate Highlights'}
                        </button>
                    </div>
                </div>
            </div>

            <div className="tiles-container">
                {loading || submitting ? (
                    <div className="loader-wrapper">
                        <Loader message={submitting ? "Submitting video..." : "Loading Streams..."}/>
                    </div>
                ) : (error || submitError) ? (
                    <div className="error-message">
                        {error ? `Error loading streams: ${error}` : `Error submitting video: ${submitError}`}
                    </div>
                ) : null}

                {data && !submitting && (
                    <>
                        <div className="tiles-grid">
                            {data.items.map((stream) => (
                                <div 
                                    className="tile" 
                                    key={stream.stream_id} 
                                    onClick={() => handleTileClick(stream)}
                                >
                                    <div className="tile-media">
                                        <img 
                                            src={constructThumbnailURL(stream.stream_id)}
                                            className="tile-image"
                                        />
                                        <div className="tile-overlay">
                                            <div className={`tile-status status-${stream.status?.toLowerCase()}`}>
                                                {stream.status || 'Ready'}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="tile-info">
                                        <div className="tile-title">
                                            {stream.stream_url.split('/').pop()}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {data.total_pages > 1 && (
                            <div className="pagination">
                                <button 
                                    className="pagination-btn" 
                                    disabled={!data.has_prev}
                                    onClick={() => goToPage(page - 1)}
                                >
                                    Previous
                                </button>
                                <span className="page-info">
                                    Page {data.page} of {data.total_pages}
                                </span>
                                <button 
                                    className="pagination-btn" 
                                    disabled={!data.has_next}
                                    onClick={() => goToPage(page + 1)}
                                >
                                    Next
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

export default Dashboard;