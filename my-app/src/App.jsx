import React, { useState, lazy, Suspense } from 'react';
import './App.css';
import FileUpload from './components/FileUpload';
import EditableList from './components/EditableList';
import ApiKeyInput from './components/ApiKeyInput';
import EvaluationTabs from './components/EvaluationTabs';
import Settings from './components/Settings';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPaperPlane, faSpinner, faBars, faExclamationTriangle, faCog, faHome } from '@fortawesome/free-solid-svg-icons';
import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

// Lazy load EvaluationTabs component
const EvaluationTabsComponent = lazy(() => import('./components/EvaluationTabs'));

function App() {
  const [cvFile, setCvFile] = useState(null);
  const [jobUrls, setJobUrls] = useState(['']);
  const [jobDescriptions, setJobDescriptions] = useState(['']);
  const [apiKey, setApiKey] = useState('');
  const [evaluations, setEvaluations] = useState([]);
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');

  // State to track if sidebar is open
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Add a state to handle the active page
  const [activePage, setActivePage] = useState('home');

  // Add a state to track current view (input form or results)
  const [currentView, setCurrentView] = useState('input');

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const handleCvChange = (e) => {
    setCvFile(e.target.files[0]);
  };

  // Function to handle navigation
  const navigateTo = (page) => {
    setActivePage(page);
    // Optionally close sidebar on mobile after navigation
    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  };

  const handleSubmit = async () => {
    const formData = new FormData();
    
    // Check if CV file is uploaded - improved validation
    if (!cvFile) {
      toast.error("Please upload your CV file before submitting");
      setLoading(false);
      
      // Highlight file upload section by scrolling to it
      const fileUploadElement = document.querySelector('.file-upload-section');
      if (fileUploadElement) {
        fileUploadElement.scrollIntoView({ behavior: 'smooth' });
        // Add a temporary highlight class
        fileUploadElement.classList.add('validation-error');
        setTimeout(() => {
          fileUploadElement.classList.remove('validation-error');
        }, 3000);
      }
      
      return; // Stop processing if no CV file
    }
    
    setLoading(true);
    setLoadingMessage('Preparing your data...');
    
    formData.append('cv', cvFile);

    const validJobUrls = jobUrls.filter((url) => url.trim() !== '');
    if (validJobUrls.length > 0) {
      formData.append('job_urls', JSON.stringify(validJobUrls));
    }

    const validJobDescriptions = jobDescriptions.filter((desc) => desc.trim() !== '');
    if (validJobDescriptions.length > 0) {
      formData.append('job_descriptions', JSON.stringify(validJobDescriptions));
    }

    if (validJobUrls.length === 0 && validJobDescriptions.length === 0) {
      toast.error("Please provide at least one job URL or description");
      setLoading(false);
      return;
    }

    if (!apiKey.trim()) {
      toast.error("API key is required");
      setLoading(false);
      navigateTo('settings');
      return;
    }
    formData.append('api_key', apiKey);

    try {
      setLoadingMessage('Analyzing your resume against job requirements...');
      
      const response = await fetch('http://localhost:8881/evaluate', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to evaluate');
      }

      const data = await response.json();
      if (data.evaluations) {
        setEvaluations(data.evaluations);
        setActiveTab(0);
        toast.success(`Successfully evaluated ${data.evaluations.length} job matches!`);
        // Switch to results view after successful evaluation
        setCurrentView('results');
      }
    } catch (error) {
      console.error("Error submitting data:", error);
      toast.error(error.message || "An error occurred during evaluation");
    }
    setLoading(false);
    setLoadingMessage('');
  };

  // Render the data input form
  const renderInputForm = () => {
    return (
      <div className="card form-card">
        <h1>Job Evaluation</h1>
        <p className="app-description">Upload your CV and enter job details to evaluate how well your profile matches with potential positions.</p>
        
        <FileUpload onFileChange={handleCvChange} />

        <EditableList
          items={jobUrls}
          setItems={setJobUrls}
          label="Job URLs:"
          placeholder="Enter job URL"
          isTextArea={false}
        />

        <EditableList
          items={jobDescriptions}
          setItems={setJobDescriptions}
          label="Job Descriptions:"
          placeholder="Enter job description"
          isTextArea={true}
        />

        <div className="submit-section">
          <button 
            onClick={handleSubmit} 
            disabled={loading}
            className="submit-button"
            title={!cvFile ? "Please upload your CV first" : "Submit for evaluation"}
          >
            {loading ? (
              <>
                <FontAwesomeIcon icon={faSpinner} spin /> 
                <span>{loadingMessage || 'Processing...'}</span>
              </>
            ) : (
              <>
                <FontAwesomeIcon icon={faPaperPlane} style={{paddingRight:4}}/> 
                <span>Evaluate My CV</span>
              </>
            )}
          </button>
          {!cvFile && (
            <div className="submit-hint">
              <FontAwesomeIcon icon={faExclamationTriangle} /> 
              Please upload your CV before submitting
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render the evaluation results
  const renderEvaluationResults = () => {
    return (
      <div className="results-container">
        <div className="results-header">
          <h2>Evaluation Results</h2>
          <button 
            className="back-button"
            onClick={() => setCurrentView('input')}
          >
            Back to Input Form
          </button>
        </div>
        <div className="card evaluation-card">
          <Suspense fallback={<div className="loading-tab">Loading evaluation results...</div>}>
            <EvaluationTabsComponent
              evaluations={evaluations}
              activeTab={activeTab}
              setActiveTab={setActiveTab}
            />
          </Suspense>
        </div>
      </div>
    );
  };

  // Render the active page content
  const renderPageContent = () => {
    switch (activePage) {
      case 'settings':
        return <Settings apiKey={apiKey} setApiKey={setApiKey} />;
      case 'home':
      default:
        // Switch between input form and results based on currentView state
        return currentView === 'input' ? renderInputForm() : renderEvaluationResults();
    }
  };

  return (
    <div className="app-wrapper">
      {/* === SIDEBAR === */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <h2>Job Evaluator</h2>
        </div>
        <nav className="sidebar-nav">
          <a 
            href="#" 
            className={`nav-item ${activePage === 'home' ? 'active' : ''}`}
            onClick={(e) => { e.preventDefault(); navigateTo('home'); }}
          >
            <FontAwesomeIcon icon={faHome} className="nav-icon" /> Home
          </a>
          <a 
            href="#" 
            className={`nav-item ${activePage === 'settings' ? 'active' : ''}`}
            onClick={(e) => { e.preventDefault(); navigateTo('settings'); }}
          >
            <FontAwesomeIcon icon={faCog} className="nav-icon" /> Settings
          </a>
        </nav>
      </aside>

      {/* === MAIN CONTENT === */}
      <div className={`main-content ${sidebarOpen ? 'sidebar-open' : ''}`}>
        {/* === TOP TOOLBAR === */}
        <nav className="top-toolbar">
          <div className="top-toolbar-left">
            <button className="sidebar-toggle" onClick={toggleSidebar}>
              <FontAwesomeIcon icon={faBars} />
            </button>
            <h3>{activePage === 'settings' ? 'Settings' : 'My Job Evaluation'}</h3>
          </div>
          <div className="top-toolbar-right">
            {activePage === 'home' && (
              <button 
                className="settings-button" 
                onClick={() => navigateTo('settings')}
                aria-label="Settings"
              >
                <FontAwesomeIcon icon={faCog} />
              </button>
            )}
          </div>
        </nav>

        {/* === PAGE CONTENT === */}
        <div className="content-container">
          {renderPageContent()}
        </div>
      </div>
      
      {/* Toast notifications */}
      <ToastContainer position="top-right" autoClose={5000} />
    </div>
  );
}

export default App;
