import { useState } from 'react';
import { API_BASE_URL } from '../constants/app.constants';

const useSubmitVideo = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const submitVideo = async (videoUrl) => {
        setLoading(true);
        setError(null);
        
        try {
            const response = await fetch(`${API_BASE_URL}/video-url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    stream_url: videoUrl
                })
            });

            if (!response.ok) {
                // Try to extract a useful message from the backend response
                let message = `HTTP error ${response.status}`;
                try {
                    const payload = await response.json();
                    message = payload?.error || payload?.message || payload?.detail || message;
                } catch (_) {
                    try {
                        const text = await response.text();
                        message = text || message;
                    } catch (_) {
                        // fall back to default message
                    }
                }
                throw new Error(message);
            }

            const data = await response.json();
            setLoading(false);
            return data;
        } catch (err) {
            setError(err.message);
            setLoading(false);
            throw err;
        }
    };

    return {
        submitVideo,
        loading,
        error
    };
};

export default useSubmitVideo;
