import React from 'react';
import './ProgressBar.css';

const ProgressBar = ({ completed, total }) => {
  const percentage = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="progress-bar">
      <div className="progress-bar-fill" style={{ width: `${percentage}%` }}></div>
    </div>
  );
};

export default ProgressBar;
