import React from 'react';
import DataAnnotation from './DataAnnotation';
import { Routes, Route } from 'react-router';
import './App.css';

function Done() {
  return (
    <div className="done-body">
      <h2>Thank you for your submission!</h2>
      <p>You can close this tab now.</p>
    </div>
  );
}

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Grasp Description Annotation</h1>
      </header>
      <main className="App-main">
        <Routes>
          <Route path="/" element={<DataAnnotation />} />
          <Route path="/done" element={<Done />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
