import React, { useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import AnnotationForm from './AnnotationForm';
import './DataAnnotation.css'; // Import the CSS file for styling

const DataAnnotation = () => {
  const [meshData, setMeshData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchMeshData = async () => {
    try {
      setLoading(true);
      setMeshData(null);
      const response = await fetch('/api/get-object-grasp', {
        method: 'POST'
      });
      const data = await response.json();
      setMeshData(data);
    } catch (error) {
      console.error('Error fetching mesh data:', error);
    } finally {
      setLoading(false);
    }
  };

  const Mesh = ({ vertices, faces, vertexColors }) => {
    const v = new Float32Array(vertices);
    const i = new Uint32Array(faces);
    const c = new Float32Array(vertexColors);
    return (
      <mesh visible position={[0, 0, 0]} rotation={[-Math.PI/2, 0, 0]}>
        <bufferGeometry attach="geometry" onUpdate={(self) => {self.computeVertexNormals()}}>
          <bufferAttribute attach="attributes-position" array={v} itemSize={3} count={v.length/3} />
          <bufferAttribute attach="attributes-color" array={c} itemSize={3} count={c.length/3} />
          <bufferAttribute attach="index" array={i} itemSize={1} count={i.length} />
        </bufferGeometry>
        <meshStandardMaterial attach="material" vertexColors={true} />
      </mesh>
    );
  };

  return (
    <div className="data-annotation-container">
      <button onClick={fetchMeshData} className="fetch-button" disabled={loading}>
        {loading ? 'Loading...' : 'Fetch Mesh'}
      </button>
      <div className="content-container">
        <div className="canvas-container">
          {loading && <div className="spinner"></div>}
          {meshData && (
            <Canvas camera={{ position: [0, 0.4, 0.6], near: 0.05, far: 20, fov: 45 }}>
              <ambientLight intensity={0.5} />
              <pointLight position={[10, 10, 10]} />
              <Mesh
                vertices={meshData.mesh.vertices}
                faces={meshData.mesh.faces}
                vertexColors={meshData.mesh.vertex_colors}
              />
              <directionalLight intensity={1} position={[10, 10, 10]} />
              <OrbitControls />
            </Canvas>
          )}
        </div>
        <AnnotationForm
          category={meshData?.object_category}
          object_id={meshData?.object_id}
          grasp_id={meshData?.grasp_id}
          fetchMesh={fetchMeshData}
        />
      </div>
    </div>
  );
};

export default DataAnnotation;
