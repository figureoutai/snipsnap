import React from 'react';

const Loader = ({message}) => {
  return (
    <div className="loader-overlay">
      <div className="loader-content">
        <div className="loader-spinner"></div>
        <div className="loader-text">{message}</div>
      </div>
    </div>
  );
};

export default Loader;