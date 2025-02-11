# Use an official Node.js runtime as a parent image
FROM node:20 AS build

# Set the working directory
WORKDIR /app

# Copy the package.json and package-lock.json files
COPY data_annotation/package*.json ./data_annotation/

# Install dependencies
RUN cd data_annotation && npm install

# Copy the rest of the application code
COPY data_annotation ./data_annotation

# Build the React app
RUN cd data_annotation && npm run build

# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY setup.py .
COPY README.md .
COPY acronym_tools .
RUN pip install --no-cache-dir -e .

# Copy the built React app from the previous stage
COPY --from=build /app/data_annotation/build ./data_annotation/build

# Copy the rest of the application code
COPY . .
RUN mkdir -p annotations
RUN chmod -R a+rw annotations

# Expose the port the app runs on
EXPOSE 8080

# Run the application
CMD ["fastapi", "run", "scripts/annotation_server.py", "--port", "8080"]
