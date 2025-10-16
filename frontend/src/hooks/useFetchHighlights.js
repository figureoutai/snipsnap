import { useParams } from "react-router";
import { useState, useCallback, useEffect } from "react";
import { API_BASE_URL } from "../constants/app.constants";

export default function useFetchHighlights() {
    const { streamId } = useParams();

    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);


    const fetchHighlights = useCallback(async (streamId) => {
        setLoading(true);
        try {
            
            // Construct URL with query parameters
            const url = new URL('highlights', API_BASE_URL);
            url.searchParams.append('stream_id', streamId);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            const data = await response.json();
            // console.log("DATA", data);
            setData({
                streamId: data['stream_id'],
                streamURL: data['stream_url'],
                status: data['status'],
                highlightsTimestamps: JSON.parse(data['highlights'])
            });
        } catch (error) {
            console.error('Error fetching stream data:', error);
            setError(error.message);
        } finally {
            setLoading(false);
        }
    }, []);


    useEffect(() => {
        if (streamId)
            fetchHighlights(streamId);
    }, [streamId, fetchHighlights]);
    return { data, loading, error };
}