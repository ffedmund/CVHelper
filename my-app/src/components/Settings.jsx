import React from 'react';
import ApiKeyInput from './ApiKeyInput';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCog, faSave } from '@fortawesome/free-solid-svg-icons';

const Settings = ({ apiKey, setApiKey }) => {
  const handleSaveSettings = () => {
    // You could add additional save functionality here if needed
    alert("Settings saved successfully!");
  };

  return (
    <div className="settings-container">
      <div className="card settings-card">
        <div className="settings-header">
          <FontAwesomeIcon icon={faCog} className="settings-icon" />
          <h1>Settings</h1>
        </div>
        
        <div className="settings-section">
          <h2>API Configuration</h2>
          <p className="settings-description">
            Configure your API credentials to use the job evaluation service.
          </p>
          
          {/* Reuse your existing ApiKeyInput component */}
          <ApiKeyInput apiKey={apiKey} setApiKey={setApiKey} />
        </div>
        
        <div className="settings-actions">
          <button className="save-settings-btn" onClick={handleSaveSettings}>
            <FontAwesomeIcon icon={faSave} /> Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings; 