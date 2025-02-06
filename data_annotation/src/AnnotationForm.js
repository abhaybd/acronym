import React, { useState } from 'react';
import { BsFillInfoCircleFill } from "react-icons/bs";
import { useNavigate } from 'react-router';
import './AnnotationForm.css';

const AnnotationForm = ({ category, object_id, grasp_id, fetchMesh, oneshot }) => {
    const navigate = useNavigate();
    const [description, setDescription] = useState('');
    const [isMalformed, setIsMalformed] = useState(false);
    const [isInvalidGrasp, setIsInvalidGrasp] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        let data, endpoint;
        if (isMalformed) {
            endpoint = "/api/submit-malformed";
            data = {
                "object_category": category,
                "object_id": object_id
            };
        } else if (isInvalidGrasp) {
            endpoint = "/api/submit-invalid-grasp";
            data = {
                "object_category": category,
                "object_id": object_id,
                "grasp_id": grasp_id
            };
        } else {
            endpoint = "/api/submit-annotation";
            data = {
                "object_category": category,
                "object_id": object_id,
                "grasp_id": grasp_id,
                "description": description
            };
        }

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
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
        if (!oneshot) {
            setDescription("");
            setIsMalformed(false);
            setIsInvalidGrasp(false);
            await fetchMesh();
        } else {
            navigate('/done', { replace: true });
        }
    };

    const isDisabled = !category || !object_id;

    return (
        <form onSubmit={handleSubmit} className="annotation-form">
            <div className="form-group">
                {category && <p>Object: {category}</p>}
            </div>
            <div className="form-group">
                <label>
                    Description:
                    <br />
                    <textarea
                        value={isMalformed || isInvalidGrasp ? "" : description}
                        onChange={(e) => setDescription(e.target.value)}
                        disabled={isMalformed || isDisabled || isInvalidGrasp}
                        required={!isMalformed && !isDisabled}
                    />
                </label>
            </div>
            <div className="form-group">
                <label title="Check if this mesh is broken (missing/transparent faces, no texturing, impossible to tell what it is)">
                    <div style={{ display: "flex", alignItems: "center" }}>
                        <BsFillInfoCircleFill color="gray" className="info-icon" />
                        <span>Mesh is malformed:</span>
                        <input
                            type="checkbox"
                            checked={isMalformed}
                            onChange={(e) => setIsMalformed(e.target.checked)}
                            disabled={isDisabled}
                        />
                    </div>
                </label>
            </div>
            <div className="form-group">
                <label title="Check if this grasp is bad (not firmly on the object, not grasping a solid part, etc)">
                    <div style={{ display: "flex", alignItems: "center" }}>
                        <BsFillInfoCircleFill color="gray" className="info-icon" />
                        <span>Invalid grasp:</span>
                        <input
                            type="checkbox"
                            checked={isInvalidGrasp && !isMalformed}
                            onChange={(e) => setIsInvalidGrasp(e.target.checked)}
                            disabled={isMalformed || isDisabled}
                        />
                    </div>
                </label>
            </div>
            <button type="submit" disabled={isDisabled} className="submit-button">Submit</button>
        </form>
    );
};

export default AnnotationForm;
