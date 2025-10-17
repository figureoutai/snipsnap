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
                throw new Error(`HTTP error! status: ${response.status}`);
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