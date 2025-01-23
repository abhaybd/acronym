import React, { useState } from 'react';

const MetadataForm = ({ onSubmit }) => {
  const [metadata, setMetadata] = useState({
    name: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setMetadata({
      ...metadata,
      [name]: value
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(metadata);
  };

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Name:
        <input type="text" name="name" value={metadata.name} onChange={handleChange} />
      </label>
      <button type="submit">Fetch Mesh</button>
    </form>
  );
};

export default MetadataForm;
