import React from 'react';

const Loader = () => {
  return (
    <div className="loader-overlay">
      <div className="loader-content">
        <div className="loader-spinner"></div>
        <div className="loader-text">Loading highlights...</div>
      </div>
    </div>
  );
};

export default Loader;