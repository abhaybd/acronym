import React, { useState } from 'react';
import { BsFillInfoCircleFill } from "react-icons/bs";
import { useNavigate } from 'react-router';
import './AnnotationForm.css';

const AnnotationForm = ({ category, object_id, grasp_id, fetchMesh, oneshot, prolific_code }) => {
    const navigate = useNavigate();
    const [description, setDescription] = useState('');
    const [isMalformed, setIsMalformed] = useState(false);
    const [isInvalidGrasp, setIsInvalidGrasp] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        let endpoint = "/api/submit-annotation";
        let data = {
            "object_category": category,
            "object_id": object_id,
            "grasp_id": grasp_id,
            "description": description,
            "is_mesh_malformed": isMalformed,
            "is_grasp_invalid": isInvalidGrasp
        };

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
        } else if (prolific_code) {
            window.location.href = `https://app.prolific.com/submissions/complete?cc=${prolific_code}`;
        } else {
            navigate('/done', { replace: true });
        }
    };

    const isDisabled = !category || !object_id || grasp_id == null;

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
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        disabled={isDisabled}
                        required={true}
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
                            checked={isInvalidGrasp}
                            onChange={(e) => setIsInvalidGrasp(e.target.checked)}
                            disabled={isDisabled}
                        />
                    </div>
                </label>
            </div>
            <button type="submit" disabled={isDisabled} className="submit-button">Submit</button>
        </form>
    );
};

export default AnnotationForm;
