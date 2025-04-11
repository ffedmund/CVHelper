import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faStar, faExternalLinkAlt, faBriefcase, faChartLine } from '@fortawesome/free-solid-svg-icons';

const EvaluationDetail = ({ evaluation }) => {
  let scoreData = null;
  try {
    // Remove markdown formatting (```json ... ```) and parse JSON
    const jsonString = evaluation.score_and_explanation.replace(/```json|```/g, '').trim();
    scoreData = JSON.parse(jsonString);
  } catch (err) {
    console.error("Error parsing score_and_explanation:", err);
  }

  // Score color based on value
  const getScoreColor = (score, total) => {
    let percentage = score / total * 100;
    if (percentage >= 80) return 'score-excellent';
    if (percentage >= 60) return 'score-good';
    if (percentage >= 40) return 'score-average';
    return 'score-poor';
  };

  // Get score label text
  const getScoreLabel = (score, total) => {
    let percentage = score / total * 100;
    if (percentage >= 80) return 'Excellent';
    if (percentage >= 60) return 'Good';
    if (percentage >= 40) return 'Average';
    return 'Poor';
  };

  return (
    <div className="evaluation-detail">
      <div className="evaluation-header">
        <div className="job-title-section">
          <h2>
          <span style={{paddingRight: 4}}><FontAwesomeIcon icon={faBriefcase} className="job-icon" /></span>
          {evaluation.job_title}</h2>
        </div>
        
        {evaluation.job_url && (
          <a 
            href={evaluation.job_url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="job-url-link"
          >
            View Job Posting <FontAwesomeIcon icon={faExternalLinkAlt} />
          </a>
        )}
      </div>

      <div className="job-description">
        <h3>Job Description</h3>
        <p>{evaluation.job_description}</p>
      </div>

      {scoreData ? (
        <div className="score-details">
          {/* New circular progress indicator for overall score */}
          <div className="score-circle-container">
            <div className="score-circle">
              <svg viewBox="0 0 100 100">
                <circle 
                  className="score-circle-bg" 
                  cx="50" 
                  cy="50" 
                  r="46"
                />
                <circle 
                  className="score-circle-progress" 
                  cx="50" 
                  cy="50" 
                  r="46"
                  strokeDasharray="289.02"
                  strokeDashoffset={289.02 - (289.02 * scoreData.overall_score) / 100}
                />
              </svg>
              <div className="score-circle-text">{scoreData.overall_score}</div>
            </div>
            <div className={`score-label ${getScoreColor(scoreData.overall_score, 100).replace('score-', '')}`}>
              {getScoreLabel(scoreData.overall_score, 100)}
            </div>
          </div>

          <div className="score-categories">
            {/* Experience score */}
            <div className="score-card">
              <div className="score-card-header">
                <h4>Experience</h4>
                <div className={`category-score ${getScoreColor(scoreData.experience.score,40)}`}>
                  {scoreData.experience.score}/40
                </div>
              </div>
              <p>{scoreData.experience.explanation}</p>
            </div>

            {/* Skills score */}
            <div className="score-card">
              <div className="score-card-header">
                <h4>Skills</h4>
                <div className={`category-score ${getScoreColor(scoreData.skills.score,40)}`}>
                  {scoreData.skills.score}/40
                </div>
              </div>
              <p>{scoreData.skills.explanation}</p>
            </div>

            {/* Personality score */}
            <div className="score-card">
              <div className="score-card-header">
                <h4>Personality</h4>
                <div className={`category-score ${getScoreColor(scoreData.personality.score,20)}`}>
                  {scoreData.personality.score}/20
                </div>
              </div>
              <p>{scoreData.personality.explanation}</p>
            </div>
          </div>

          <div className="overall-explanation">
            <h4>Summary</h4>
            <div className="explanation-card">
              <p>{scoreData.overall_explanation}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="raw-evaluation">
          <pre>{evaluation.score_and_explanation}</pre>
        </div>
      )}
    </div>
  );
};

export default EvaluationDetail;