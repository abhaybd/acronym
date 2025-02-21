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
            Given a 3D object and a grasp, users should input the following:
          </p>
          <ul>
            <li>A brief description of the object</li>
            <li>A description of the grasp relative to the object</li>
            <li>Whether the mesh is malformed</li>
            <li>Whether the grasp is good, bad, or infeasible</li>
          </ul>
          <p>
            If the mesh is malformed or the grasp is infeasible, users should select the corresponding options, and still provide a best-effort grasp description.
          </p>

          <h3>Object Description</h3>
          <p>
            The <strong>Object Description</strong> should be a brief description of the object in about 10 words or less.
            This description should be concise and descriptive, e.g. "This is a red coffee mug with white handle".
          </p>

          <h3>Grasp Description</h3>
          <img src={teapot_img} alt="Teapot example" className="tutorial-image" />
          <p>
            The <strong>Grasp Description</strong> should be a concise and detailed explanation of the grasp's position and orientation relative to the displayed object.
          </p>
          <p>
            The description should only be about the grasp, not about it's appropriateness or quality.
            For example, do not say that the grasp is good or bad, or comment on its stability.
            Additionally, do not describe where a better grasp would be.
          </p>
          <p>
            For example, shown this teapot, a possible description could be:
          </p>
          <blockquote>
            The grasp is on the spout of the teapot, where it connects to the body.
            The grasp is oriented parallel to the base of the teapot, and the fingers are closing on either side of the spout.
          </blockquote>

          <h3>Malformed Mesh</h3>
          <img src={malformed_mesh_img} alt="Malformed mesh example" className="tutorial-image" />
          <p>
            The <strong>Malformed Mesh</strong> option is for when a mesh is broken, due to bad textures or invisible walls.
            For example, the texture on this milk carton is broken, causing it to appear completely black.
            This object should be marked as a malformed mesh.
          </p>
          <p>
            In general, a mesh should be marked as malformed if it's difficult to tell what the object is.
          </p>

          <h3>Grasp Label</h3>
          <img src={invalid_grasp_img} alt="Invalid grasp example" className="tutorial-image" />
          <p>
            The <strong>Grasp Label</strong> dropdown corresponds to the appropriateness of the grasp.
          </p>
          <ul>
            <li>A good grasp is a grasp that makes sense and is appropriate, e.g. grasping a pan from the handle.</li>
            <li>A bad grasp is a grasp that doesn't make sense or is inappropriate, e.g. grasping a fork by the tines.</li>
            <li>A physically infeasible grasp is neither good nor bad, since it's impossible. These grasps should be marked as infeasible.</li>
          </ul>
          <p>
            For example, the grasp shown above is on the wafts of steam from a mug.
            This grasp is infeasible, since steam can't be grasped.
          </p>
          <p>
            Some grasps may be difficult to categorize, but do your best to choose the most appropriate label.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Tutorial;
