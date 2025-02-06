from fastapi import FastAPI, Cookie, Response
from pydantic import BaseModel
import os
import asyncio

import h5py
import trimesh
import numpy as np

from acronym_tools import load_mesh, load_grasps, create_gripper_marker
from annotation import Object, Annotation, MalformedAnnotation, InvalidGraspAnnotation

DATA_ROOT = os.environ.get("DATA_ROOT", "data")
ANNOTATIONS_ROOT = "annotations"
ANNOTATION_PATH = f"{ANNOTATIONS_ROOT}/annotations.jsonl"
MALFORMED_PATH = f"{ANNOTATIONS_ROOT}/malformed.jsonl"
INVALID_GRASPS_PATH = f"{ANNOTATIONS_ROOT}/invalid_grasps.jsonl"

with open("categories.txt", "r") as f:
    CATEGORIES = set(f.read().splitlines())

# maps (category, object_id, grasp_id) -> whether the grasp is annotated
annotated_grasps: dict[str, dict[str, dict[int, bool]]] = {}
annotation_lock = asyncio.Lock()
annotation_file_lock = asyncio.Lock()
malformed_file_lock = asyncio.Lock()
invalid_grasp_file_lock = asyncio.Lock()

for fn in os.listdir(f"{DATA_ROOT}/grasps"):
    category, obj_id = fn.split("_", 1)
    obj_id = obj_id[:-len(".h5")]
    if category in CATEGORIES:
        with h5py.File(f"{DATA_ROOT}/grasps/{fn}", "r") as f:
            idxs = np.array(f["grasps/sampled_idxs"])
            succs = np.array(f["grasps/qualities/flex/object_in_gripper"], dtype=bool)[idxs]
            idxs = idxs[succs]
        if category not in annotated_grasps:
            annotated_grasps[category] = {}
        annotated_grasps[category][obj_id] = {i: False for i in idxs}

def remove_grasp(category, obj_id, grasp_id):
    if category in annotated_grasps and obj_id in annotated_grasps[category] and grasp_id in annotated_grasps[category][obj_id]:
        del annotated_grasps[category][obj_id][grasp_id]
        if len(annotated_grasps[category][obj_id]) == 0:
            remove_object(category, obj_id)

def remove_object(category, obj_id):
    if obj_id in annotated_grasps[category]:
        del annotated_grasps[category][obj_id]
        if len(annotated_grasps[category]) == 0:
            del annotated_grasps[category]

os.makedirs(ANNOTATIONS_ROOT, exist_ok=True)
if os.path.isfile(ANNOTATION_PATH):
    with open(ANNOTATION_PATH, "r") as f:
        for line in f:
            annotation = Annotation.model_validate_json(line)
            annotated_grasps[annotation.obj.object_category][annotation.obj.object_id][annotation.grasp_id] = True
if os.path.isfile(MALFORMED_PATH):
    with open(MALFORMED_PATH, "r") as f:
        for line in f:
            annotation = MalformedAnnotation.model_validate_json(line)
            remove_object(annotation.obj.object_category, annotation.obj.object_id)
if os.path.isfile(INVALID_GRASPS_PATH):
    with open(INVALID_GRASPS_PATH, "r") as f:
        for line in f:
            annotation = InvalidGraspAnnotation.model_validate_json(line)
            remove_grasp(annotation.obj.object_category, annotation.obj.object_id, annotation.grasp_id)

def num_annotations_category(category: str):
    n_annotations = 0
    for grasps in annotated_grasps[category].values():
        n_annotations += sum(grasps.values())
    return n_annotations

def num_annotations(category: str, obj_id: str):
    return sum(annotated_grasps[category][obj_id].values())

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
async def get_object_grasp(response: Response):
    async with annotation_lock:
        category = choose_from_least(annotated_grasps.keys(), num_annotations_category)
        obj_id = choose_from_least(annotated_grasps[category], key=lambda oid: num_annotations(category, oid))
        unannotated_grasps = [grasp_id for grasp_id, annotated in annotated_grasps[category][obj_id].items() if not annotated]

    if len(unannotated_grasps) == 0:
        print("All grasps annotated!")
        response.status_code = 204
        return ObjectGraspInfo(object_category="", object_id="", grasp_id=-1)

    grasp_id = np.random.choice(unannotated_grasps)
    print(f"Chose {category}_{obj_id} with {num_annotations(category, obj_id)} annotations")

    return ObjectGraspInfo(
        object_category=category,
        object_id=obj_id,
        grasp_id=grasp_id
    )

@app.post("/api/get-mesh-data", response_model=MeshData)
async def get_mesh_data(request: ObjectGraspInfo):
    category, obj_id, grasp_id = request.object_category, request.object_id, request.grasp_id
    object_mesh: trimesh.Trimesh = load_mesh(f"{DATA_ROOT}/grasps/{category}_{obj_id}.h5", "data")
    T, _ = load_grasps(f"{DATA_ROOT}/grasps/{category}_{obj_id}.h5")
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
    async with annotation_lock:
        total_annotations = sum(map(num_annotations_category, annotated_grasps.keys()))
    print(f"User {user_id} annotated: {request.object_category}_{request.object_id}, grasp {request.grasp_id}. Total annotations: {total_annotations+1}")
    category = request.object_category
    obj_id = request.object_id
    grasp_id = request.grasp_id

    annotated_grasps[category][obj_id][grasp_id] = True
    annotation = Annotation(
        obj=Object(object_category=category, object_id=obj_id),
        grasp_id=grasp_id,
        description=request.description,
        user_id=user_id
    )
    async with annotation_file_lock:
        with open(ANNOTATION_PATH, "a+") as f:
            f.write(f"{annotation.model_dump_json()}\n")

@app.post("/api/submit-malformed")
async def malformed_mesh(request: MalformedMeshSubmission, user_id: str = Cookie(...)):
    print(f"User {user_id} marked as malformed: {request.object_category}_{request.object_id}")
    annotation = MalformedAnnotation(
        obj=Object(object_category=request.object_category, object_id=request.object_id),
        user_id=user_id
    )
    async with annotation_lock:
        remove_object(request.object_category, request.object_id)
    async with malformed_file_lock:
        with open(MALFORMED_PATH, "a+") as f:
            f.write(f"{annotation.model_dump_json()}\n")

@app.post("/api/submit-invalid-grasp")
async def invalid_grasp(request: ObjectGraspInfo, user_id: str = Cookie(...)):
    category = request.object_category
    obj_id = request.object_id
    grasp_id = request.grasp_id
    print(f"User {user_id} marked as invalid grasp: {category}_{obj_id}, grasp {grasp_id}")
    annotation = InvalidGraspAnnotation(
        obj=Object(object_category=category, object_id=obj_id),
        grasp_id=grasp_id,
        user_id=user_id
    )
    async with annotation_lock:
        remove_grasp(category, obj_id, grasp_id)
    async with invalid_grasp_file_lock:
        with open(INVALID_GRASPS_PATH, "a+") as f:
            f.write(f"{annotation.model_dump_json()}\n")
