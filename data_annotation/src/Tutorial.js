import React from 'react';
import { FaTimes } from 'react-icons/fa';
import teapot_img from "./tutorial_teapot.png";
import invalid_grasp_img from "./tutorial_invalid_grasp.png";
import malformed_mesh_img from "./tutorial_malformed_mesh.png";
import './Tutorial.css';

const Tutorial = ({ onClose }) => {
  return (
    <div className="tutorial-overlay">
      <div className="tutorial-popup">
        <button className="close-button" onClick={onClose}>
          <FaTimes />
        </button>
        <div className="tutorial-content">
          <h2>Tutorial</h2>
          <p>
              This is a data annotation tool for semantic grasping.
              Users are shown a 3D object and a grasp, and can rotate and zoom the object by clicking and dragging in the 3D viewer to get a better view.
              Given this visualization, users should input the following:
              <ul>
                <li>A description of the grasp relative to the object</li>
                <li>Whether the mesh is malformed</li>
                <li>Whether the grasp is invalid</li>
              </ul>
              If the mesh is malformed or the grasp is invalid, users should check the corresponding checkboxes, and still provide a best-effort grasp description.
          </p>

          <h3>Grasp Description</h3>
          <img src={teapot_img} alt="Teapot example" className="tutorial-image" />
          <p>Shown this teapot, a possible description could be:</p>
          <blockquote>
            The grasp is on the spout of the teapot, where it connects to the body.
            The grasp is oriented parallel to the base of the teapot, and the fingers are closing on either side of the spout.
          </blockquote>

          <h3>Malformed Mesh</h3>
          <img src={malformed_mesh_img} alt="Malformed mesh example" className="tutorial-image" />
          <p>
            The <strong>Malformed Mesh</strong> checkbox is for when a mesh is broken, due to bad textures or invisible walls.
            For example, the texture on this milk carton is broken, causing it to appear completely black.
            This object should be marked as a malformed mesh.
          </p>
          <p>
            In general, if you can't tell what the mesh is supposed to be, mark it as malformed.
          </p>

          <h3>Invalid Grasp</h3>
          <img src={invalid_grasp_img} alt="Invalid grasp example" className="tutorial-image" />
          <p>
            The <strong>Invalid Grasp</strong> checkbox is for when the grasp is physically infeasible, or isn't grasping a rigid part of the object.
            For example, the grasp shown here is on the wafts of steam from a mug.
            This grasp is infeasible, since steam can't be grasped, so this grasp should be marked as invalid.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Tutorial;


