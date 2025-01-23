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

class AnnotationRequest(BaseModel):
    username: str
    object_category: str
    object_id: str
    grasp_id: int

@app.post("/api/get-object-grasp", response_model=MeshResponse)
async def get_object_grasp():
    category = "Pan"
    # category = min(CATEGORIES, key=num_annotations_category)
    obj_id = min(annotation_counts[category], key=lambda oid: len(annotation_counts[category][oid]))

    object_mesh: trimesh.Trimesh = load_mesh(f"data/grasps/{category}_{obj_id}.h5", "data")
    visual: trimesh.visual.ColorVisuals = object_mesh.visual

    # inorder_vertices = object_mesh.vertices[object_mesh.faces.flatten()]
    # inorder_colors = visual.vertex_colors[object_mesh.faces.flatten(),:3] / 255.

    return MeshResponse(
        object_category=category,
        object_id=obj_id,
        grasp_id=0,
        mesh={
            "vertices": object_mesh.vertices.flatten().tolist(),
            "faces": object_mesh.faces.flatten().tolist(),
            "vertex_colors": (visual.vertex_colors[:,:3] / 255).flatten().tolist(),
            "normals": object_mesh.vertex_normals.flatten().tolist(),
        }
    )

@app.post("/submit-annotation")
async def submit_annotation(request: AnnotationRequest):
    category = request.object_category
    obj_id = request.object_id
    grasp_id = request.grasp_id

    annotation_counts[category][obj_id].add(grasp_id)

    return {"success": True}

