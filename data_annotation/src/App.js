import React, { useEffect } from 'react';
import DataAnnotation from './DataAnnotation';
import Quiz from './Quiz';
import { Routes, Route } from 'react-router';
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
          <Route path="/quiz" element={<Quiz />} />
          <Route path="/done" element={<Done />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
