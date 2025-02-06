import React, { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import AnnotationForm from './AnnotationForm';
import { createSearchParams, useNavigate, useSearchParams } from 'react-router';
import './DataAnnotation.css';

const DataAnnotation = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [meshData, setMeshData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchObjectInfo = async () => {
    setLoading(true);
    setMeshData(null);
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
        searchParams.has('object_id') &&
        searchParams.has('grasp_id')) {
      fetchMeshData(
        searchParams.get("object_category"),
        searchParams.get('object_id'),
        searchParams.get('grasp_id')
      );
    }
  }, [searchParams]);

  const fetchMeshData = async (category, obj_id, grasp_id) => {
    try {
      const response = await fetch('/api/get-mesh-data', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          object_category: category,
          object_id: obj_id,
          grasp_id: grasp_id
        }),
      });
      if (!response.ok) {
        alert(`Failed to submit annotation: HTTP ${response.status}`);
        const errorMessage = await response.text();
        console.error(errorMessage);
      } else {
        const data = await response.json();
        setMeshData(data);
      }
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

  const oneshot = searchParams.get('oneshot') === 'true';

  return (
    <div className="data-annotation-container">
      <button onClick={fetchObjectInfo} className="fetch-button" disabled={loading} hidden={oneshot}>
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
                vertices={meshData.vertices}
                faces={meshData.faces}
                vertexColors={meshData.vertex_colors}
              />
              <directionalLight intensity={1} position={[10, 10, 10]} />
              <OrbitControls />
            </Canvas>
          )}
        </div>
        <AnnotationForm
          category={searchParams.get("object_category")}
          object_id={searchParams.get('object_id')}
          grasp_id={searchParams.get('grasp_id')}
          fetchMesh={fetchObjectInfo}
          oneshot={oneshot}
        />
      </div>
    </div>
  );
};

export default DataAnnotation;
