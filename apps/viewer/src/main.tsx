/** Viewer entry point. Research prototype - Not for clinical use. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('Missing #root container in index.html');
createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
