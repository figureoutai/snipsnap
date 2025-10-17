import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import useFetchStreams from '../../hooks/useFetchStreams';
import useSubmitVideo from '../../hooks/useSubmitVideo';
import Loader from '../../components/Loader';
import Header from '../../components/Header';
import Modal from '../../components/Modal';
import { constructThumbnailURL } from '../../utils/assetURL';
import { isValidVideoURL } from '../../utils/common.utils';
import { GENERIC_VIDEO_SUBMIT_ERROR, INVALID_VIDEO_URL_MESSAGE, PROCESSING_INFO_MESSAGE } from "../../constants/message.constants";
import { POLLING_TIME_INTERVAL_IN_SECONDS } from '../../constants/app.constants';
import '../../styles/dashboard.css';


function Dashboard() {
    const navigate = useNavigate();
    const [searchQuery, setSearchQuery] = useState('');
    const { submitVideo, loading: submitting, error: submitError } = useSubmitVideo();

    const timerRef = useRef(null);

    // Modal states
    const [showModal, setShowModal] = useState(false);
    const [modalContent, setModalContent] = useState({
        type: 'info',
        title: '',
        message: ''
    });

    // Initialize with 12 items per page for a 3x4 grid
    const {
        data,
        loading,
        error,
        page,
        goToPage,
        setItemsPerPage,
        refresh
    } = useFetchStreams(1, 12);

    const handleTileClick = useCallback((stream) => {
        if (stream.status === 'COMPLETED') {
            navigate(`/highlights/${stream.stream_id}`);
        }
    }, [navigate]);

    // Function to show the modal
    const showModalMessage = useCallback((type, title, message) => {
        setModalContent({ type, title, message });
        setShowModal(true);
    }, []);


    /**
     * polling logic, refresh the endpoint for every 30 seconds
     * repeat the polling until no submitted or in progress items
     */
    useEffect(() => {
        if (!data)
            return;

        const nonCompletedItems = data.items
            .map((item) => item.status)
            .filter((status) => (status === 'SUBMITTED' || status === 'IN_PROGRESS'));

        if (nonCompletedItems.length) {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
                timerRef.current = null;
            }

            timerRef.current = setTimeout(() => refresh(), POLLING_TIME_INTERVAL_IN_SECONDS * 1000);
            return;
        }
    }, [data, refresh]);


    const handleGenerate = useCallback(async () => {
        if (!searchQuery.trim()) {
            return;
        }

        if (!isValidVideoURL(searchQuery)) {
            showModalMessage(
                'error',
                INVALID_VIDEO_URL_MESSAGE.title,
                INVALID_VIDEO_URL_MESSAGE.description
            );
            return;
        }

        try {
            // Show info modal about video processing limit
            showModalMessage(
                'info',
                PROCESSING_INFO_MESSAGE.title,
                PROCESSING_INFO_MESSAGE.description
            );

            // Wait a moment for user to read the message
            await new Promise(resolve => setTimeout(resolve, 2000));

            // await submitVideo(searchQuery.trim());
            setSearchQuery(''); // Clear input after successful submission
            await refresh(); // Refresh the streams list
        } catch (err) {
            console.error('Failed to submit video:', err);
            showModalMessage(
                'error',
                GENERIC_VIDEO_SUBMIT_ERROR.title,
                err.message || GENERIC_VIDEO_SUBMIT_ERROR.description
            );
        }
    }, [searchQuery, submitVideo, refresh]);


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
                        <Loader message={submitting ? "Submitting video..." : "Loading Streams..."} />
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
                                            onError={(e) => {
                                                e.target.src = '/placeholder-image.png';
                                            }}
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

            {/* Modal Component */}
            <Modal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                type={modalContent.type}
                title={modalContent.title}
                message={modalContent.message}
            />
        </div>
    );
}

export default Dashboard;