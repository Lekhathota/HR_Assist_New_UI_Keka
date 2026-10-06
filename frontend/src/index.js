import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { AppearanceProvider } from './components/AppearanceProvider.jsx';
// Load the reference theme after every existing page stylesheet.
import './styles/reference-theme.css';
import './styles/analytics.css';
import './styles/shell.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<AppearanceProvider><App /></AppearanceProvider>);
