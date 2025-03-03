import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import ObjectViewer from './ObjectViewer';
import AnnotationForm from './AnnotationForm';
import Tutorial from './Tutorial';
import ProgressBar from './ProgressBar';
import './DataAnnotation.css';
import { BsBoxArrowUpRight } from 'react-icons/bs';

const DataAnnotation = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [annotSchedule, setAnnotSchedule] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);

  const encodeStr = (str) => {
    return encodeURIComponent(btoa(str));
  };

  const decodeStr = (str) => {
    return atob(decodeURIComponent(str));
  };

  const navigateToSchedule = (schedule) => {
    searchParams.set("annotation_schedule", encodeStr(JSON.stringify(schedule)));
    navigate({
      pathname: "/",
      search: searchParams.toString()
    }, {replace: true});
  };

  const fetchObjectInfo = async () => {
    setLoading(true);
    const response = await fetch('/api/get-object-info', {
      method: 'POST'
    });
    if (!response.ok) {
      alert(`Failed to fetch object info: HTTP ${response.status}`);
      const errorMessage = await response.text();
      console.error(errorMessage);
      setLoading(false);
    } else if (response.status === 204) {
      alert("No more objects to annotate!");
      navigate('/done', { replace: true });
    } else {
      const data = await response.json();
      const schedule = {
        idx: 0,
        annotations: [data]
      };
      navigateToSchedule(schedule);
    }
  };

  /*
  Schedule looks like:
  {
    idx: int,
    annotations: [
      {
        object_category: str,
        object_id: str,
        grasp_id: int
      },
      ...
    ]
  }
  */

  useEffect(() => {
    if (searchParams.has("annotation_schedule")) {
      setLoading(true);
      const schedule = JSON.parse(decodeStr(searchParams.get("annotation_schedule")));
      const idx = schedule.idx;
      if (idx >= schedule.annotations.length || idx < 0) {
        alert("Invalid schedule index!");
        return;
      }
      setAnnotSchedule(schedule);
    }
  }, [searchParams]);

  const oneshot = searchParams.get('oneshot') === 'true' || searchParams.has("prolific_code");

  const onFormSubmit = async () => {
    if (annotSchedule.idx + 1 === annotSchedule.annotations.length) {
      if (!oneshot) {
        await fetchObjectInfo();
      } else if (searchParams.has("prolific_code")) {
        window.location.href = `https://app.prolific.com/submissions/complete?cc=${searchParams.get("prolific_code")}`;
      } else {
        navigate('/done', { replace: true });
      }
    } else {
      const newSchedule = { ...annotSchedule, idx: annotSchedule.idx + 1 };
      navigateToSchedule(newSchedule);
    }
  };

  const annotInfo = annotSchedule ? annotSchedule.annotations[annotSchedule.idx] : null;

  return (
    <div className="data-annotation-container">
      <div className="button-container">
        <button className="ai2-button" onClick={fetchObjectInfo} disabled={loading} hidden={oneshot}>
          {loading ? 'Loading...' : 'Fetch Mesh'}
        </button>
        <button className="ai2-button" onClick={() => setShowTutorial(true)}>Show Tutorial</button>
        <button className="ai2-button" onClick={() => window.open("/reference", '_blank')}>
          Show Examples
        <BsBoxArrowUpRight style={{marginLeft: "5px"}} />
        </button>
      </div>
      {annotSchedule && annotSchedule.annotations.length > 1 && (
        <div className="progress-container">
          <span>{annotSchedule.idx}/{annotSchedule.annotations.length}</span>
          <ProgressBar completed={annotSchedule.idx} total={annotSchedule.annotations.length} />
        </div>
      )}

      <div className={`content-container ${showTutorial ? 'dimmed' : ''}`}>
        <div className="object-viewer-container">
          <ObjectViewer
            object_category={annotInfo?.object_category}
            object_id={annotInfo?.object_id}
            grasp_id={annotInfo?.grasp_id}
            onFinishedLoading={() => setLoading(false)}
          />
        </div>
        <AnnotationForm
          category={annotInfo?.object_category}
          object_id={annotInfo?.object_id}
          grasp_id={annotInfo?.grasp_id}
          onSubmit={onFormSubmit}
          prolific_code={searchParams.get('prolific_code')}
        />
      </div>
      {showTutorial && <Tutorial onClose={() => setShowTutorial(false)} />}
    </div>
  );
};

export default DataAnnotation;
