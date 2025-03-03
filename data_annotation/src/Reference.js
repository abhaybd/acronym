import React from 'react';
import ObjectViewer from './ObjectViewer';
import './Reference.css';

// Import the questions from Practice.js to stay in sync
import { QUESTIONS } from './Practice';

const Reference = () => {
  return (
    <div className="references-container">
      <h2>Reference Answers</h2>
      <p>Here are examples of good grasp descriptions:</p>

      <div className="reference-list">
        {QUESTIONS.map((question, index) => (
          <div key={index} className="reference-item">
            <div className="reference-viewer">
              <ObjectViewer
                object_category={question.object.object_category}
                object_id={question.object.object_id}
                grasp_id={question.object.grasp_id}
              />
            </div>
            <div className="reference-text">
              <h3>{question.object.object_category}</h3>
              <blockquote>{question.answers.find(a => a.correct)?.text}</blockquote>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Reference; 