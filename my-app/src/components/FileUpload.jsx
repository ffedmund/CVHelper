import React, { useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faFileAlt, faUpload, faTimes, faExclamationTriangle } from '@fortawesome/free-solid-svg-icons';

const FileUpload = ({ onFileChange }) => {
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState('');
  const [showReminder, setShowReminder] = useState(false);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFileName(e.dataTransfer.files[0].name);
      setShowReminder(false);
      onFileChange({ target: { files: [e.dataTransfer.files[0]] } });
    }
  };

  const handleChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFileName(e.target.files[0].name);
      setShowReminder(false);
      onFileChange(e);
    }
  };

  const clearFile = () => {
    setFileName('');
    onFileChange({ target: { files: null } });
  };

  // This method can be called externally to show the reminder
  React.useEffect(() => {
    // Check if this component has the validation-error class
    const checkForValidationError = () => {
      const element = document.querySelector('.file-upload-section');
      if (element && element.classList.contains('validation-error')) {
        setShowReminder(true);
      }
    };

    // Set up a mutation observer to watch for class changes
    const observer = new MutationObserver(checkForValidationError);
    const element = document.querySelector('.file-upload-section');
    
    if (element) {
      observer.observe(element, { 
        attributes: true, 
        attributeFilter: ['class'] 
      });
    }

    return () => observer.disconnect();
  }, []);

  return (
    <div className="section file-upload-section">
      <label>Upload CV File:</label>
      {showReminder && (
        <div className="file-upload-reminder">
          <FontAwesomeIcon icon={faExclamationTriangle} className="reminder-icon" />
          <span>Please upload your CV file - this is required</span>
        </div>
      )}
      <div 
        className={`file-upload-area ${dragActive ? 'drag-active' : ''} ${showReminder ? 'highlight-required' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {fileName ? (
          <div className="file-selected">
            <FontAwesomeIcon icon={faFileAlt} className="file-icon" />
            <span className="file-name">{fileName}</span>
            <button 
              type="button" 
              className="clear-file" 
              onClick={clearFile}
              aria-label="Remove file"
            >
              <FontAwesomeIcon icon={faTimes} />
            </button>
          </div>
        ) : (
          <>
            <FontAwesomeIcon icon={faUpload} className="upload-icon" />
            <p>Drag and drop your CV here or click to browse</p>
            <p className="required-field-text">* Required</p>
            <input 
              type="file" 
              id="cv-upload" 
              onChange={handleChange} 
              accept=".pdf,.doc,.docx" 
              className="file-input" 
            />
          </>
        )}
      </div>
      <p className="input-help-text">Accepted formats: PDF, DOC, DOCX</p>
    </div>
  );
};

export default FileUpload;
