from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

import trimesh
import h5py

from acronym_tools import load_mesh, load_grasps, create_gripper_marker

with open("categories.txt", "r") as f:
    CATEGORIES = f.read().splitlines()

annotation_counts: dict[str, dict[str, set[int]]] = {}
for c in CATEGORIES:
    annotation_counts[c] = {}
for fn in os.listdir(f"data/grasps"):
    category, obj_id = fn.split("_", 1)
    obj_id = obj_id[:-len(".h5")]
    if category in annotation_counts:
        annotation_counts[category][obj_id] = set()

def num_annotations_category(category: str):
    return sum(map(len, annotation_counts[category].values()))

app = FastAPI()

class UserRequest(BaseModel):
    username: str

class MeshResponse(BaseModel):
    object_category: str
    object_id: str
    grasp_id: int
    mesh: dict

class AnnotationSubmission(BaseModel):
    username: str
    object_category: str
    object_id: str
    grasp_id: int
    description: str

class MalformedMeshSubmission(BaseModel):
    username: str
    object_category: str
    object_id: str

@app.post("/api/get-object-grasp", response_model=MeshResponse)
async def get_object_grasp():
    category = "Pan"
    # category = min(CATEGORIES, key=num_annotations_category)
    import numpy as np
    category = CATEGORIES[np.random.randint(len(CATEGORIES))]
    obj_id = np.random.choice(list(annotation_counts[category].keys()))
    # obj_id = min(annotation_counts[category], key=lambda oid: len(annotation_counts[category][oid]))

    object_mesh: trimesh.Trimesh = load_mesh(f"data/grasps/{category}_{obj_id}.h5", "data")
    visual: trimesh.visual.ColorVisuals = object_mesh.visual

    # TODO: select grasp and render

    return MeshResponse(
        object_category=category,
        object_id=obj_id,
        grasp_id=0,
        mesh={
            "vertices": object_mesh.vertices.flatten().tolist(),
            "faces": object_mesh.faces.flatten().tolist(),
            "vertex_colors": (visual.vertex_colors[:,:3] / 255).flatten().tolist(),
        }
    )

@app.post("/api/submit-annotation")
async def submit_annotation(request: AnnotationSubmission):
    category = request.object_category
    obj_id = request.object_id
    grasp_id = request.grasp_id

    annotation_counts[category][obj_id].add(grasp_id)
    print(request)

@app.post("/api/submit-malformed")
async def malformed_mesh(request: MalformedMeshSubmission):
    print(request)
