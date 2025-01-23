import React from 'react';
import DataAnnotation from './DataAnnotation';
import './App.css'; // Import the CSS file for styling

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Grasp Description Annotation</h1>
      </header>
      <main className="App-main">
        <DataAnnotation />
      </main>
    </div>
  );
}

export default App;
