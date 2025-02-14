import React, { Suspense, useEffect, useState, useRef } from 'react';
import { Canvas, useLoader } from '@react-three/fiber';
import { OrbitControls, Environment } from '@react-three/drei';
import { createSearchParams, useNavigate, useSearchParams } from 'react-router';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import AnnotationForm from './AnnotationForm';
import Tutorial from './Tutorial';
import './DataAnnotation.css';

const DataAnnotation = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [meshURL, setMeshURL] = useState(null);
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

  const fetchObjectInfo = async () => {
    setLoading(true);
    setMeshURL(null);
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
      navigate({
        pathname: "/",
        search: createSearchParams(data).toString()
      }, {replace: true});
    }
  };

  useEffect(() => {
    if (searchParams.has("object_category") &&
        searchParams.has("object_id") &&
        searchParams.has("grasp_id")) {
      setLoading(true);
      setMeshURL(`/api/get-mesh-data/${searchParams.get("object_category")}/${searchParams.get("object_id")}/${searchParams.get("grasp_id")}`);
    } else if (searchParams.has("object_category") ||
          searchParams.has("object_id") ||
          searchParams.has("grasp_id")) {
        alert("Invalid search parameters! Need all of object_category, object_id, and grasp_id.");
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

  return (
    <div className="data-annotation-container">
      <div className="button-container">
        <button className="ai2-button" onClick={fetchObjectInfo} disabled={loading} hidden={oneshot}>
          {loading ? 'Loading...' : 'Fetch Mesh'}
        </button>
        <button className="ai2-button" onClick={() => setShowTutorial(true)}>Show Tutorial</button>
      </div>
      <div className={`content-container ${showTutorial ? 'dimmed' : ''}`}>
        <div className="canvas-container-toolbar">
          <div className="canvas-container">
            {loading && <div className="spinner"></div>}
            {meshURL && (
              <Canvas camera={{ position: [0, 0.4, 0.6], near: 0.05, far: 20, fov: 45 }}>
                <Suspense fallback={null}>
                  <Environment preset="sunset" />
                  <OrbitControls ref={orbitRef} />
                  <GLTFMesh
                    meshURL={meshURL}
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
          category={searchParams.get("object_category")}
          object_id={searchParams.get('object_id')}
          grasp_id={searchParams.get('grasp_id')}
          fetchMesh={fetchObjectInfo}
          oneshot={oneshot}
          prolific_code={searchParams.get('prolific_code')}
        />
      </div>
      {showTutorial && <Tutorial onClose={() => setShowTutorial(false)} />}
    </div>
  );
};

export default DataAnnotation;
