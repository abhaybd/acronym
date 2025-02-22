import React, { Suspense, useEffect, useState, useRef } from 'react';
import { Canvas, useLoader } from '@react-three/fiber';
import { OrbitControls, Environment } from '@react-three/drei';
import { createSearchParams, useNavigate, useSearchParams } from 'react-router';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import AnnotationForm from './AnnotationForm';
import Tutorial from './Tutorial';
import ProgressBar from './ProgressBar';
import './DataAnnotation.css';

const DataAnnotation = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [annotSchedule, setAnnotSchedule] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const orbitRef = useRef();

  useEffect(() => {
    THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1);
  }, []);

  useEffect(() => {
    const hasSeenTutorial = localStorage.getItem('hasSeenTutorial');
    if (!hasSeenTutorial) {
      setShowTutorial(true);
      localStorage.setItem('hasSeenTutorial', 'true');
    }
  }, []);

  const encodeStr = (str) => {
    return encodeURIComponent(btoa(str));
  };

  const decodeStr = (str) => {
    return atob(decodeURIComponent(str));
  };

  const navigateToSchedule = (schedule) => {
    searchParams.set("annotation_schedule", encodeStr(JSON.stringify(schedule)));
    console.log(searchParams.get("annotation_schedule"), JSON.stringify(schedule));
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

  const GLTFMesh = ({ meshURL }) => {
    const gltf = useLoader(GLTFLoader, meshURL);

    useEffect(() => {
      setLoading(false);
    }, [gltf]);

    return (
      <primitive object={gltf.scene} />
    );
  };

  const oneshot = searchParams.get('oneshot') === 'true' || searchParams.has("prolific_code");

  const onFormSubmit = async () => {
    if (annotSchedule.idx + 1 == annotSchedule.annotations.length) {
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

  const getProgress = () => {
    if (!annotSchedule) return { completed: 0, total: 0 };
    return { completed: annotSchedule.idx, total: annotSchedule.annotations.length };
  };

  return (
    <div className="data-annotation-container">
      <div className="button-container">
        <button className="ai2-button" onClick={fetchObjectInfo} disabled={loading} hidden={oneshot}>
          {loading ? 'Loading...' : 'Fetch Mesh'}
        </button>
        <button className="ai2-button" onClick={() => setShowTutorial(true)}>Show Tutorial</button>
      </div>
      {annotSchedule && annotSchedule.annotations.length > 1 && (
        <div className="progress-container">
          <span>{annotSchedule.idx}/{annotSchedule.annotations.length}</span>
          <ProgressBar completed={annotSchedule.idx} total={annotSchedule.annotations.length} />
        </div>
      )}

      <div className={`content-container ${showTutorial ? 'dimmed' : ''}`}>
        <div className="canvas-container-toolbar">
          <div className="canvas-container">
            {loading && <div className="spinner"></div>}
            {annotInfo && (
              <Canvas camera={{ position: [0, 0.4, 0.6], near: 0.05, far: 20, fov: 45 }}>
                <Suspense fallback={null}>
                  <Environment preset="sunset" />
                  <OrbitControls ref={orbitRef} />
                  <GLTFMesh
                    meshURL={`/api/get-mesh-data/${annotInfo.object_category}/${annotInfo.object_id}/${annotInfo.grasp_id}`}
                  />
                </Suspense>
              </Canvas>
            )}
          </div>
          <div className="canvas-toolbar">
            <p className='instructions'>Left click + drag to rotate, right click + drag to pan, scroll to zoom.</p>
            <button onClick={() => orbitRef.current.reset()} className="ai2-button" disabled={!orbitRef.current}>Reset View</button>
          </div>
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
