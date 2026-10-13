import React from 'react';
import ReactDOM from 'react-dom/client';
// Bundled rather than loaded from CDNs, which some company networks block.
import '@fortawesome/fontawesome-free/css/all.min.css';
import 'flatpickr/dist/flatpickr.min.css';
import './index.css';
import App from './App.jsx';
import { AppearanceProvider } from './components/AppearanceProvider.jsx';
// Load the reference theme after every existing page stylesheet.
import './styles/reference-theme.css';
import './styles/analytics.css';
import './styles/shell.css';
import './styles/responsive.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<AppearanceProvider><App /></AppearanceProvider>);
