import { useParams } from "react-router";
import { useState, useCallback, useEffect } from "react";
import { API_BASE_URL } from "../constants/app.constants";

/**
 * Response structure
 * response = {
    items: [
        {
            "stream_id": "a63855eb",
            "stream_url": "./data/test_videos/news.mp4",
            "highlights": null,
            "status": "IN_PROGRESS",
            "message": null
        }
    ],
    "total": 46,
    "page": 1,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false,
    "limit": 20
}
 */


export default function useFetchStreams(initialPage = 1, initialLimit = 20) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [page, setPage] = useState(initialPage);
    const [limit, setLimit] = useState(initialLimit);

    const fetchStreams = useCallback(async (page, limit) => {
        setLoading(true);
        try {
            // Construct URL with query parameters
            const url = new URL('streams', API_BASE_URL);
            url.searchParams.append('page', page);
            url.searchParams.append('limit', limit);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                throw new Error('Failed to fetch streams');
            }

            const responseData = await response.json();
            
            // Parse the highlights JSON string for each item
            const processedData = {
                ...responseData,
                items: responseData.items.map(item => ({
                    ...item,
                    highlights: item.highlights ? JSON.parse(item.highlights) : null
                }))
            };
            
            setData(processedData); // Contains items with parsed highlights, total, page, total_pages, etc.
        } catch (error) {
            console.error('Error fetching streams:', error);
            setError(error.message);
        } finally {
            setLoading(false);
        }
    }, []);

    // Fetch streams when page or limit changes
    useEffect(() => {
        fetchStreams(page, limit);
    }, [page, limit, fetchStreams]);

    // Function to change page
    const goToPage = useCallback((newPage) => {
        setPage(newPage);
    }, []);

    // Function to change items per page
    const setItemsPerPage = useCallback((newLimit) => {
        setLimit(newLimit);
        setPage(1); // Reset to first page when changing limit
    }, []);

    return {
        data,           // Contains items array and pagination metadata
        loading,
        error,
        page,          // Current page
        limit,         // Items per page
        goToPage,      // Function to change page
        setItemsPerPage, // Function to change items per page
        refresh: () => fetchStreams(page, limit), // Function to manually refresh
    };
}