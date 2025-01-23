import React, { useState } from 'react';
import './AnnotationForm.css'; // Import the CSS file for styling

const AnnotationForm = ({ category, object_id, grasp_id, fetchMesh }) => {
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [isMalformed, setIsMalformed] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        let data, endpoint;
        if (isMalformed) {
            endpoint = "/api/submit-malformed";
            data = {
                "username": name,
                "object_category": category,
                "object_id": object_id
            };
        } else {
            endpoint = "/api/submit-annotation";
            data = {
                "username": name,
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
        setDescription("");
        setIsMalformed(false);
        await fetchMesh();
    };

    const isDisabled = !category || !object_id;

    return (
        <form onSubmit={handleSubmit} className="annotation-form">
            <div className="form-group">
                <label>
                    Name:
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                    />
                </label>
            </div>
            <div className="form-group">
                <label>
                    Description:
                    <textarea
                        value={isMalformed ? "" : description}
                        onChange={(e) => setDescription(e.target.value)}
                        disabled={isMalformed || isDisabled}
                        required={!isMalformed && !isDisabled}
                    />
                </label>
            </div>
            <div className="form-group">
                <label>
                    Mesh is malformed:
                    <input
                        type="checkbox"
                        checked={isMalformed}
                        onChange={(e) => setIsMalformed(e.target.checked)}
                        disabled={isDisabled}
                    />
                </label>
            </div>
            <button type="submit" disabled={isDisabled} className="submit-button">Submit & Fetch Mesh</button>
        </form>
    );
};

export default AnnotationForm;
