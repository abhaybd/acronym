import React, { useEffect, useState } from 'react';
import { BsFillInfoCircleFill } from "react-icons/bs";
import { v4 as uuidv4 } from 'uuid';
import './AnnotationForm.css';

const AnnotationForm = ({ category, object_id, grasp_id, onSubmit, prolific_code }) => {
    const [objDescription, setObjDescription] = useState('');
    const [graspDescription, setGraspDescription] = useState('');
    const [isMalformed, setIsMalformed] = useState('');
    const [graspLabel, setGraspLabel] = useState('');
    const [startTime, setStartTime] = useState(null);
    const [userID, setUserID] = useState("");

    useEffect(() => {
        let user_id = localStorage.getItem("user_id");
        if (!user_id) {
            user_id = uuidv4();
            localStorage.setItem("user_id", user_id);
        }
        if (!prolific_code) {
            setUserID(user_id);
        }
    }, [prolific_code]);

    const resetForm = () => {
        setObjDescription("");
        setGraspDescription("");
        setIsMalformed("");
        setGraspLabel("");
    };

    useEffect(() => {
        setStartTime(Date.now());
        resetForm();
    }, [category, object_id, grasp_id]);

    const handleSubmit = async (e) => {
        e.preventDefault();

        try {
            const response = await fetch("/api/submit-annotation", {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    "obj": {
                        "object_category": category,
                        "object_id": object_id,
                    },
                    "grasp_id": grasp_id,
                    "obj_description": objDescription,
                    "grasp_description": graspDescription,
                    "is_mesh_malformed": isMalformed === 'yes',
                    "grasp_label": graspLabel,
                    "user_id": userID,
                    "time_taken": (Date.now() - startTime) / 1000,
                }),
            });

            if (!response.ok) {
                alert(`Failed to submit annotation: HTTP ${response.status}`);
                const errorMessage = await response.text();
                console.error(errorMessage);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred while submitting the annotation');
        }

        resetForm();
        await onSubmit();
    };

    const isDisabled = !category || !object_id || grasp_id == null;

    return (
        <form onSubmit={handleSubmit} className="annotation-form">
            <div className="form-group">
                {category && <p>Object: {category}</p>}
            </div>
            <div className="form-group" hidden={!prolific_code}>
                <label>
                    User ID:
                    <br />
                    <input
                        type="text" value={userID}
                        onChange={e => setUserID(e.target.value)}
                        required={true} />
                </label>
            </div>
            <div className="form-group">
                <label>
                    Object Description (10 words or less):
                    <br />
                    <textarea
                        className="object-description-input"
                        placeholder="This is a(n) ..."
                        value={objDescription}
                        onChange={(e) => setObjDescription(e.target.value)}
                        disabled={isDisabled}
                        required={true}
                        minLength={5}
                    />
                </label>
            </div>
            <div className="form-group">
                <label>
                    Grasp Description:
                    <br />
                    <textarea
                        className="grasp-description-input"
                        placeholder="The grasp is ..."
                        value={graspDescription}
                        onChange={(e) => setGraspDescription(e.target.value)}
                        disabled={isDisabled}
                        required={true}
                        minLength={20}
                    />
                </label>
            </div>
            <div className="form-group">
                <label title="Select if this mesh is broken (missing/transparent faces, no texturing, impossible to tell what it is)">
                    <div style={{ display: "flex", alignItems: "center" }}>
                        <BsFillInfoCircleFill color="gray" className="info-icon" />
                        <span>Mesh is malformed:</span>
                        <select
                            value={isMalformed}
                            onChange={(e) => setIsMalformed(e.target.value)}
                            disabled={isDisabled}
                            required
                        >
                            <option value="" disabled></option>
                            <option value="no">No</option>
                            <option value="yes">Yes</option>
                        </select>
                    </div>
                </label>
            </div>
            <div className="form-group">
                <label className="form-label" title="Select the appropriateness of the grasp, see tutorial for details">
                    <div style={{ display: "flex", alignItems: "center" }}>
                        <BsFillInfoCircleFill color="gray" className="info-icon" />
                        <span>Grasp Label:</span>
                        <select
                            value={graspLabel}
                            onChange={(e) => setGraspLabel(e.target.value)}
                            disabled={isDisabled}
                            required
                        >
                            <option value="" disabled></option>
                            <option value="good">Good Grasp</option>
                            <option value="bad">Bad Grasp</option>
                            <option value="infeasible">Infeasible Grasp</option>
                        </select>
                    </div>
                </label>
            </div>
            <button type="submit" disabled={isDisabled} className="ai2-button">Submit</button>
        </form>
    );
};

export default AnnotationForm;
