import React from 'react';
import './styles.css';

const Modal = ({ isOpen, onClose, type = 'info', title, message }) => {
    if (!isOpen) return null;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <div className={`modal-header ${type}`}>
                    <h2 className="modal-title">{title}</h2>
                    <button className="modal-close" onClick={onClose}>×</button>
                </div>
                <div className="modal-body">
                    <p>{message}</p>
                </div>
                <div className="modal-footer">
                    <button className={`modal-button ${type}`} onClick={onClose}>
                        {type === 'error' ? 'Close' : 'Got it'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Modal;