import React, { useEffect } from 'react';
import DataAnnotation from './DataAnnotation';
import Practice from './Practice';
import Reference from './Reference';
import { Routes, Route, Navigate } from 'react-router';
import './App.css';
import * as THREE from 'three';

function Done() {
  return (
    <div className="done-body">
      <h2>Thank you for your submission!</h2>
      <p>You can close this tab now.</p>
    </div>
  );
}

function NotFound() {
  return (
    <div className="not-found-body">
      <h2>404 Not Found</h2>
    </div>
  );
}

function App() {
  // set the default up vector for three.js
  useEffect(() => {
    THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1);
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Grasp Description Annotation</h1>
      </header>
      <main className="App-main">
        <Routes>
          <Route path="/" element={<DataAnnotation />} />
          <Route path="/practice" element={<Practice />} />
          <Route path="/done" element={<Done />} />
          <Route path="/reference" element={<Reference />} />
          <Route path="/404" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/404" />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
