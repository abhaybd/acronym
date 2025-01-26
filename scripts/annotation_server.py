from fastapi import FastAPI, Cookie
from pydantic import BaseModel
import os

import trimesh
import numpy as np

from acronym_tools import load_mesh, load_grasps, create_gripper_marker
from annotation import Object, Annotation, MalformedAnnotation

with open("categories.txt", "r") as f:
    CATEGORIES = f.read().splitlines()

annotation_counts: dict[str, dict[str, set[int]]] = {}
malformed_counts: dict[str, dict[str, set[str]]] = {}
for c in CATEGORIES:
    annotation_counts[c] = {}
    malformed_counts[c] = {}
for fn in os.listdir(f"data/grasps"):
    category, obj_id = fn.split("_", 1)
    obj_id = obj_id[:-len(".h5")]
    if category in annotation_counts:
        annotation_counts[category][obj_id] = set()
        malformed_counts[category][obj_id] = set()

if os.path.isfile("annotations.jsonl"):
    with open("annotations.jsonl", "r") as f:
        for line in f:
            annotation = Annotation.model_validate_json(line)
            annotation_counts[annotation.obj.object_category][annotation.obj.object_id].add(annotation.grasp_id)
if os.path.isfile("malformed.jsonl"):
    with open("malformed.jsonl", "r") as f:
        for line in f:
            annotation = MalformedAnnotation.model_validate_json(line)
            malformed_counts[annotation.obj.object_category][annotation.obj.object_id].add(annotation.user_id)
            if annotation.obj.object_id in annotation_counts[annotation.obj.object_category]:
                del annotation_counts[annotation.obj.object_category][annotation.obj.object_id]

def num_annotations_category(category: str):
    return sum(map(len, annotation_counts[category].values()))

def choose_from_least(arr, key):
    if not isinstance(arr, list):
        arr = list(arr)
    min_val = min(map(key, arr))
    min_elem_idxs = [i for i, elem in enumerate(arr) if key(elem) == min_val]
    return arr[np.random.choice(min_elem_idxs)]

app = FastAPI()

class UserRequest(BaseModel):
    username: str

class ObjectGraspInfo(BaseModel):
    object_category: str
    object_id: str
    grasp_id: int

class MeshData(BaseModel):
    vertices: list[float]
    faces: list[int]
    vertex_colors: list[float]

class AnnotationSubmission(BaseModel):
    object_category: str
    object_id: str
    grasp_id: int
    description: str

class MalformedMeshSubmission(BaseModel):
    object_category: str
    object_id: str

@app.post("/api/get-object-info", response_model=ObjectGraspInfo)
async def get_object_grasp():
    category = "Pan"
    category = choose_from_least(annotation_counts.keys(), num_annotations_category)
    obj_id = choose_from_least(annotation_counts[category], key=lambda oid: len(annotation_counts[category][oid]))

    _, success = load_grasps(f"data/grasps/{category}_{obj_id}.h5")
    successful_grasp_ids = np.argwhere(success == 1).flatten()
    grasp_id = np.random.choice(successful_grasp_ids)

    return ObjectGraspInfo(
        object_category=category,
        object_id=obj_id,
        grasp_id=grasp_id
    )

@app.post("/api/get-mesh-data", response_model=MeshData)
async def get_mesh_data(request: ObjectGraspInfo):
    category, obj_id, grasp_id = request.object_category, request.object_id, request.grasp_id
    object_mesh: trimesh.Trimesh = load_mesh(f"data/grasps/{category}_{obj_id}.h5", "data")
    T, _ = load_grasps(f"data/grasps/{category}_{obj_id}.h5")
    gripper_marker: trimesh.Trimesh = create_gripper_marker(color=[0, 255, 0]).apply_transform(T[grasp_id])
    gripper_marker.vertices -= object_mesh.centroid
    object_mesh.vertices -= object_mesh.centroid

    scene = trimesh.Scene([object_mesh, gripper_marker])
    geom: trimesh.Trimesh = scene.to_mesh()
    visual: trimesh.visual.ColorVisuals = geom.visual

    return MeshData(
        vertices=geom.vertices.flatten().tolist(),
        faces=geom.faces.flatten().tolist(),
        vertex_colors=(visual.vertex_colors[:,:3] / 255).flatten().tolist(),
    )

@app.post("/api/submit-annotation")
async def submit_annotation(request: AnnotationSubmission, user_id: str = Cookie(...)):
    total_annotations = sum(map(num_annotations_category, annotation_counts.keys()))
    print(f"User {user_id} annotated: {request.object_category}_{request.object_id}, grasp {request.grasp_id}. Total annotations: {total_annotations+1}")
    category = request.object_category
    obj_id = request.object_id
    grasp_id = request.grasp_id

    annotation_counts[category][obj_id].add(grasp_id)
    annotation = Annotation(
        obj=Object(object_category=category, object_id=obj_id),
        grasp_id=grasp_id,
        description=request.description,
        user_id=user_id
    )
    with open("annotations.jsonl", "a+") as f:
        f.write(f"{annotation.model_dump_json()}\n")

@app.post("/api/submit-malformed")
async def malformed_mesh(request: MalformedMeshSubmission, user_id: str = Cookie(...)):
    print(f"User {user_id} marked as malformed: {request.object_category}_{request.object_id}")
    annotation = MalformedAnnotation(
        obj=Object(object_category=request.object_category, object_id=request.object_id),
        user_id=user_id
    )
    if request.object_id in annotation_counts[request.object_category]:
        del annotation_counts[request.object_category][request.object_id]
    with open("malformed.jsonl", "a+") as f:
        f.write(f"{annotation.model_dump_json()}\n")
