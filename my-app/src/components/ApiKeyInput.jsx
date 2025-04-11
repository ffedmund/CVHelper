import React, { useState, useEffect } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faKey, faEye, faEyeSlash } from '@fortawesome/free-solid-svg-icons';

const ApiKeyInput = ({ apiKey, setApiKey }) => {
  const [showApiKey, setShowApiKey] = useState(false);
  
  // Load API key from local storage on component mount
  useEffect(() => {
    const storedApiKey = localStorage.getItem('apiKey');
    if (storedApiKey) {
      setApiKey(storedApiKey);
    }
  }, [setApiKey]);

  // Save API key to local storage whenever it changes
  const handleApiKeyChange = (e) => {
    const newApiKey = e.target.value;
    setApiKey(newApiKey);
    localStorage.setItem('apiKey', newApiKey);
  };

  return (
    <div className="section api-key-section">
      <label htmlFor="api-key">API Key:</label>
      <div className="input-with-icon">
        <FontAwesomeIcon icon={faKey} className="input-icon" />
        <input
          id="api-key"
          type={showApiKey ? "text" : "password"}
          placeholder="Enter your API key"
          value={apiKey}
          onChange={handleApiKeyChange}
          className="api-key-input"
        />
        <button 
          type="button" 
          className="toggle-visibility" 
          onClick={() => setShowApiKey(!showApiKey)}
          aria-label={showApiKey ? "Hide API key" : "Show API key"}
        >
          <FontAwesomeIcon icon={showApiKey ? faEyeSlash : faEye} />
        </button>
      </div>
      <p className="input-help-text">Your API key is stored locally and never shared.</p>
    </div>
  );
};

export default ApiKeyInput;