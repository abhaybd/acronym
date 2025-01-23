import React, { useEffect } from 'react';
import DataAnnotation from './DataAnnotation';
import './App.css'; // Import the CSS file for styling
import { useCookies } from 'react-cookie';
import { v4 as uuidv4 } from 'uuid';

function App() {
  const [cookies, setCookie] = useCookies(['user_id']);
  useEffect(() => {
    if (!cookies.user_id) {
      const expires = new Date(Date.now() + 1000 * 60 * 60 * 24 * 365); // 1 year
      setCookie('user_id', uuidv4(), { path: '/', expires: expires });
    }
  }, []);

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
