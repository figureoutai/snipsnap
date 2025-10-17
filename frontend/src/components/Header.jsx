import React from 'react';
import { Link } from 'react-router';
import { APP_NAME } from "../constants/app.constants";
import '../styles/headerStyle.css'

function Header() {
    return (
        <header className="app-header">
            <div className="header-content">
                <Link to="/" className="app-title">
                    {APP_NAME}
                </Link>
            </div>
        </header>
    );
}

export default Header;