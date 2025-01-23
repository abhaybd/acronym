import React, { useState, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three'; // Import THREE namespace
import MetadataForm from './MetadataForm';

const MeshViewer = () => {
  const [meshData, setMeshData] = useState(null);

  const fetchMeshData = async (metadata) => {
    try {
      const response = await fetch('/api/get-object-grasp', {
        method: 'POST'
      });
      const data = await response.json();
      setMeshData(data);
    } catch (error) {
      console.error('Error fetching mesh data:', error);
    }
  };

  const Mesh = ({ vertices, faces, normals, vertexColors }) => {
    // const geometry = React.useMemo(() => {
    //   const geom = new THREE.BufferGeometry();
    //   geom.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    //   geom.setAttribute('color', new THREE.Float32BufferAttribute(vertexColors, 3));
    //   geom.setIndex(faces);
    //   return geom;
    // }, [vertices, faces, vertexColors]);

  //   return (
  //     <mesh geometry={geometry}>
  //       <meshBasicMaterial vertexColors={true} wireframe />
  //     </mesh>
  //   );
  const v = new Float32Array(vertices);
  const i = new Uint32Array(faces);
  const c = new Float32Array(vertexColors);
  const n = new Float32Array(normals);
  return (
    <mesh visible position={[0, 0, 0]}>
      <bufferGeometry attach="geometry">
        <bufferAttribute attach="attributes-position" array={v} itemSize={3} count={v.length/3} />
        <bufferAttribute attach="attributes-color" array={c} itemSize={3} count={c.length/3} />
        <bufferAttribute attach="attributes-normal" array={n} itemSize={3} count={n.length/3} />
        <bufferAttribute attach="index" array={i} itemSize={1} count={i.length} />
      </bufferGeometry>
      {/* <meshNormalMaterial attach="material" /> */}
      <meshStandardMaterial attach="material" vertexColors={true} />
      {/* <meshBasicMaterial attach="material" vertexColors={true} /> */}
    </mesh>
    );
  };

  return (
    <div>
      <MetadataForm onSubmit={fetchMeshData} />
      <div style={{ width: '800px', height: '600px' }}>
        {meshData && (
          <Canvas shadows={"soft"}>
            <ambientLight />
            <pointLight position={[10, 10, 10]} />
            <Mesh
              vertices={meshData.mesh.vertices}
              faces={meshData.mesh.faces}
              normals={meshData.mesh.normals}
              vertexColors={meshData.mesh.vertex_colors}
            />
            <OrbitControls />
          </Canvas>
        )}
      </div>
    </div>
  );
};

export default MeshViewer;
