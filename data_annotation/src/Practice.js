import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import ObjectViewer from './ObjectViewer';
import Tutorial from './Tutorial';
import './Practice.css';

export const QUESTIONS = [
  {
    object: {
      object_category: "Mug",
      object_id: "128ecbc10df5b05d96eaf1340564a4de_0.0013421115752322193",
      grasp_id: 1326
    },
    answers: [
      {
        id: 'a',
        text: "This is a good grasp since it's on the handle of the mug. It's stable and secure.",
        feedback: "Incorrect. The description should not include judgments about the grasp quality or stability.",
      },
      {
        id: 'b',
        text: "The grasp is on the middle of the handle of the mug, coming from above and to the side at an angle. The fingers are grasping either side of the handle.",
        feedback: "Correct! This description focuses on the position and orientation of the grasp without judging its quality.",
        correct: true,
      },
      {
        id: 'c',
        text: "The grasp is on the handle of the mug, grasping the sides. However, it's coming at an angle, and should be straight on instead.",
        feedback: "Incorrect. The description should not suggest alternative grasp locations or judge the grasp quality.",
      },
      {
        id: 'd',
        text: "The robot is trying to lift the mug by the handle, which may cause it to spill due to the angle.",
        feedback: "Incorrect. The description should not speculate about outcomes or consequences of the grasp.",
      }
    ]
  },
  {
    object: {
      object_category: "Pan",
      object_id: "c8b06a6cb1a910c38e43a810a63361f0_3.666323933306171e-05",
      grasp_id: 529
    },
    answers: [
      {
        id: 'a',
        text: "The grasp is on the rim of the pan, which is suboptimal since the pan may be hot.",
        feedback: "Incorrect. The description should not include judgments about the grasp quality or stability.",
      },
      {
        id: 'b',
        text: "The grasp is on the wrong side of the pan, coming from above and grasping the inside and outside of the pan's rim.",
        feedback: "Incorrect. The description should not include judgments about whether the grasp is right or wrong.",
      },
      {
        id: 'c',
        text: "The grasp is on the rim of the pan, approximately opposite the handle. It is oriented vertically and grasping the inside and outside of the pan's rim.",
        feedback: "Correct! This description focuses on the position and orientation of the grasp without judging its quality.",
        correct: true,
      },
      {
        id: 'd',
        text: "The grasp is on the rim of the pan, opposite the handle.",
        feedback: "Incorrect. While factual, the description should also include information about the orientation of the grasp.",
      }
    ]
  },
  {
    object: {
      object_category: "WineGlass",
      object_id: "2d89d2b3b6749a9d99fbba385cc0d41d_0.0024652679182251653",
      grasp_id: 1298
    },
    answers: [
      {
        id: 'a',
        text: "The grasp is on the base of the wine glass, oriented at an angle. The fingers are grasping the top and bottom of the base.",
        feedback: "Correct! This description focuses on the position and orientation of the grasp without judging its quality.",
        correct: true,
      },
      {
        id: 'b',
        text: "The grasp is on the bottom of the wine glass, The fingers will collide with the table, since they are holding the top and bottom.",
        feedback: "Incorrect. The description should not extend beyond the grasp to describe interactions with the environment.",
      },
      {
        id: 'c',
        text: "The robot is grasping the flat part on the bottom of the wine glass.",
        feedback: "Incorrect. The description should only be a factual description of the grasp, not a comment on what is doing the grasping, which may or may not be a robot.",
      },
      {
        id: 'd',
        text: "The grasp is infeasible, since the fingers are not aligned with the base of the wine glass.",
        feedback: "Incorrect. The description should not include judgments about the feasibility of the grasp.",
      }
    ]
  }
];

const Practice = () => {
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const [submittedAnswers, setSubmittedAnswers] = useState(new Set());
  const [showTutorial, setShowTutorial] = useState(false);
  const [correctAnswers, setCorrectAnswers] = useState(0);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const currentQuestion = QUESTIONS[currentQuestionIdx];

  useEffect(() => {
    const lastPassedTime = localStorage.getItem('practicePassedTime');
    if (lastPassedTime) {
      const hoursSincePass = (Date.now() - parseInt(lastPassedTime)) / (1000 * 60 * 60);
      if (hoursSincePass < 24) {
        navigate({
          pathname: '/',
          search: searchParams.toString()
        }, {replace: true});
        return;
      }
    }
  }, [navigate, searchParams]);

  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem('hasSeenTutorial');
    if (!hasSeenTutorial) {
      setShowTutorial(true);
      localStorage.setItem('hasSeenTutorial', 'true');
    }
  }, []);

  const handleSubmit = () => {
    if (selectedAnswer === null) return;
    
    const isCorrect = currentQuestion.answers.find(a => a.id === selectedAnswer)?.correct ?? false;
    if (isCorrect && submittedAnswers.size === 0) {  // Only count if first attempt
      setCorrectAnswers(prev => prev + 1);
    }

    setShowFeedback(true);
    setSubmittedAnswers(prev => new Set([...prev, selectedAnswer]));
  };

  const handleContinue = () => {
    if (currentQuestionIdx === QUESTIONS.length - 1) {
      if (correctAnswers / QUESTIONS.length >= 0.5) {
        localStorage.setItem('practicePassedTime', Date.now().toString());
        navigate({
          pathname: '/',
          search: searchParams.toString()
        }, {replace: true});
      } else {
        if (searchParams.has("prolific_rejection_code")) {
          window.location.href = `https://app.prolific.com/submissions/complete?cc=${searchParams.get("prolific_rejection_code")}`;
        } else {
          alert("Sorry, you did not answer a sufficient number of questions correctly. You will be redirected shortly.");
          setTimeout(() => {
            navigate('/done', {replace: true});
          }, 3000);
        }
      }
    } else {
      setCurrentQuestionIdx(prev => prev + 1);
      setSelectedAnswer(null);
      setShowFeedback(false);
      setSubmittedAnswers(new Set());
    }
  };

  return (
    <div className="quiz-container">
      <div className="button-container top">
        <button className="ai2-button" onClick={() => setShowTutorial(true)}>Show Tutorial</button>
      </div>

      <h2>Practice Question {currentQuestionIdx + 1} of {QUESTIONS.length}</h2>
      <p>
        Please read the tutorial closely before answering the following practice questions.
        Getting too many questions wrong will result in a request for your submission to be returned.
      </p>
      <p>
        Which of the following would be the most appropriate grasp description for this image?
      </p>
      
      <div className={`quiz-content ${showTutorial ? 'dimmed' : ''}`}>
        <div className="quiz-image-container">
          <ObjectViewer
            object_category={currentQuestion.object.object_category}
            object_id={currentQuestion.object.object_id}
            grasp_id={currentQuestion.object.grasp_id}
          />
        </div>
        
        <div className="quiz-options">
          <div className="answer-container">
            {currentQuestion.answers.map((answer) => (
              <div key={answer.id} className="answer-option">
                <div className="answer-option-content">
                  <input
                    type="radio"
                    id={answer.id}
                    name="quiz-answer"
                    value={answer.id}
                    checked={selectedAnswer === answer.id}
                    onChange={(e) => setSelectedAnswer(e.target.value)}
                    disabled={submittedAnswers.has(answer.id)}
                  />
                  <label 
                    htmlFor={answer.id} 
                    className={submittedAnswers.has(answer.id) ? 'disabled' : ''}
                  >
                    {answer.text}
                  </label>
                </div>
                {showFeedback && submittedAnswers.has(answer.id) && (
                  <div className={`feedback ${answer.correct ? 'correct' : 'incorrect'}`}>
                    {answer.feedback}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="button-container">
            <button 
              className="quiz-submit-button" 
              onClick={handleSubmit}
              disabled={selectedAnswer === null || submittedAnswers.has(selectedAnswer)}
            >
              Submit
            </button>
            {showFeedback && submittedAnswers.has(currentQuestion.answers.find(a => a.correct)?.id) && (
              <button 
                className="quiz-submit-button" 
                onClick={handleContinue}
              >
                {currentQuestionIdx === QUESTIONS.length - 1 ? 'Finish' : 'Continue'}
              </button>
            )}
          </div>
        </div>
      </div>
      {showTutorial && <Tutorial onClose={() => setShowTutorial(false)} />}
    </div>
  );
};

export default Practice;