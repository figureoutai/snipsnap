import React, { useCallback } from 'react';
import { useNavigate } from 'react-router';
import '../../styles/dashboard.css';

const mockData = [
    {
        highlightId: '123',
        fileName: 'Sample Video'
    }
];


function Dashboard() {
    const navigate = useNavigate();

    const handleTileClick = useCallback((data) => {
        navigate(`/highlights/${data.highlightId}`);
    }, [navigate]);

    const handleGenerate = useCallback(() => {
        console.log('GENERATE');
    }, []);

    return (
        <div className='dashboard-container'>

            <div class="header">
                <div class="search-container">
                    <div class="search-wrapper">
                        <input type="text" class="search-bar" placeholder="Search dashboard..." />
                        <button class="generate-btn" onClick={handleGenerate}>Generate</button>
                    </div>
                </div>
            </div>

            <div class="tiles-container">
                <div class="tiles-grid">
                    {
                        mockData.map((item, index) => {

                            return (
                                <div class="tile" key={index} onClick={() => handleTileClick(item)}>
                                    <div class="tile-icon">📊</div>
                                    <div class="tile-title">{item.fileName}</div>
                                </div>
                            );
                        })
                    }
                </div>
            </div>
        </div>
    );
}

export default Dashboard;