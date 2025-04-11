import React from 'react';
import EvaluationDetail from './EvaluationDetail';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBriefcase } from '@fortawesome/free-solid-svg-icons';

const EvaluationTabs = ({ evaluations, activeTab, setActiveTab }) => {
  if (!evaluations || evaluations.length === 0) {
    return null;
  }

  return (
    <div className="evaluation-tabs">
      <h2 className="evaluations-heading">Your Job Match Results</h2>
      <div className="tab-headers">
        {evaluations.map((evalItem, index) => (
          <button
            key={index}
            onClick={() => setActiveTab(index)}
            className={`tab-button ${activeTab === index ? 'active' : ''}`}
          >
            <FontAwesomeIcon icon={faBriefcase} className="tab-icon" />
            <span className="tab-label">{evalItem.job_title}</span>
          </button>
        ))}
      </div>
      <div className="tab-content">
        <EvaluationDetail evaluation={evaluations[activeTab]} />
      </div>
    </div>
  );
};

export default EvaluationTabs;