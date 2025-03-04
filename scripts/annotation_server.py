from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import asyncio
from tempfile import TemporaryDirectory
import io
from fastapi.responses import FileResponse
from fastapi import HTTPException

import h5py
import trimesh
import numpy as np
import pickle
import boto3
import re

from acronym_tools import create_gripper_marker
from annotation import Annotation

s3 = boto3.client("s3")

BUCKET_NAME = "prior-datasets"
DATA_PREFIX = "semantic-grasping/acronym/"
ANNOTATION_PREFIX = "semantic-grasping/annotations/"

if "ANNOT_CATEGORIES" in os.environ:
    CATEGORIES = set(s.strip() for s in os.environ["ANNOT_CATEGORIES"].split(","))
else:
    with open("categories.txt", "r") as f:
        CATEGORIES = set(f.read().splitlines())

# maps (category, object_id, grasp_id) -> whether the grasp is annotated
annotated_grasps: dict[str, dict[str, dict[int, bool]]] = {}
annotation_lock = asyncio.Lock()

# load annotation skeleton
skeleton_bytes = io.BytesIO()
s3.download_fileobj(BUCKET_NAME, f"{DATA_PREFIX}annotation_skeleton.pkl", skeleton_bytes)
skeleton_bytes.seek(0)
skeleton: dict[str, dict[str, dict[int, bool]]] = pickle.load(skeleton_bytes)
for category, objs in skeleton.items():
    annotated_grasps[category] = {}
    for obj_id, grasps in objs.items():
        if len(grasps) > 0:
            annotated_grasps[category][obj_id] = grasps

assert all(c in annotated_grasps for c in CATEGORIES), "Some categories are missing from the annotation skeleton!"

print("Loading existing annotations...")
continuation_token = None
while True:
    list_kwargs = {"Bucket": BUCKET_NAME, "Prefix": ANNOTATION_PREFIX}
    if continuation_token:
        list_kwargs["ContinuationToken"] = continuation_token
    response = s3.list_objects_v2(**list_kwargs)

    if "Contents" in response:
        for obj in response["Contents"]:
            key = obj["Key"]
            if key.endswith(".json"):
                filename = os.path.basename(key)[:-len(".json")]
                object_category, object_id, grasp_id, _ = filename.split("__")
                grasp_id = int(grasp_id)
                if object_category in annotated_grasps and \
                    object_id in annotated_grasps[object_category] and \
                    grasp_id in annotated_grasps[object_category][object_id]:
                    annotated_grasps[object_category][object_id][grasp_id] = True

    if response.get("IsTruncated"):
        continuation_token = response["NextContinuationToken"]
    else:
        break
print("Done!")


def num_annotations_category(category: str):
    n_annotations = 0
    for grasps in annotated_grasps[category].values():
        n_annotations += sum(grasps.values())
    return n_annotations

def num_unannotated_category(category: str):
    n_unannotated = 0
    for grasps in annotated_grasps[category].values():
        n_unannotated += sum(1 for annotated in grasps.values() if not annotated)
    return n_unannotated

def num_annotations(category: str, obj_id: str):
    return sum(annotated_grasps[category][obj_id].values())

def num_unannotated(category: str, obj_id: str):
    return sum(1 for annotated in annotated_grasps[category][obj_id].values() if not annotated)

def sample_choice(arr, key):
    if not isinstance(arr, list):
        arr = list(arr)
    weights = np.array([key(elem) for elem in arr])
    assert np.all(weights >= 0)
    if np.all(weights == 0):
        return None
    idx = np.random.choice(len(arr), p=weights/weights.sum())
    return arr[idx]

def load_object_data(category: str, obj_id: str) -> tuple[trimesh.Scene, np.ndarray]:
    datafile_key = f"{DATA_PREFIX}grasps/{category}_{obj_id}.h5"
    with TemporaryDirectory() as tmpdir:
        datafile_path = os.path.join(tmpdir, "data.h5")
        s3.download_file(BUCKET_NAME, datafile_key, datafile_path)
        with h5py.File(datafile_path, "r") as f:
            mesh_fname: str = f["object/file"][()].decode("utf-8")
            mtl_fname = mesh_fname[:-len(".obj")] + ".mtl"
            mesh_path = os.path.join(tmpdir, os.path.basename(mesh_fname))
            mtl_path = os.path.join(tmpdir, os.path.basename(mtl_fname))
            mesh_pfx = DATA_PREFIX + os.path.dirname(mesh_fname) + "/"
            s3.download_file(BUCKET_NAME, f"{DATA_PREFIX}{mesh_fname}", mesh_path)
            s3.download_file(BUCKET_NAME, f"{DATA_PREFIX}{mtl_fname}", mtl_path)
            with open(mtl_path, "r") as mtl_f:
                for line in mtl_f.read().splitlines():
                    if m := re.fullmatch(r".+ (.+\.jpg)", line):
                        texture_fname = m.group(1)
                        assert texture_fname == os.path.basename(texture_fname), texture_fname
                        texture_path = os.path.join(tmpdir, texture_fname)
                        s3.download_file(BUCKET_NAME, f"{mesh_pfx}{texture_fname}", texture_path)

            T = np.array(f["grasps/transforms"])
            mesh_scale = f["object/scale"][()]
        obj_mesh = trimesh.load(mesh_path)
        obj_mesh = obj_mesh.apply_scale(mesh_scale)
        if isinstance(obj_mesh, trimesh.Scene):
            scene = obj_mesh
        elif isinstance(obj_mesh, trimesh.Trimesh):
            scene = trimesh.Scene([obj_mesh])
        else:
            raise ValueError("Unsupported geometry type")
    return scene, T

app = FastAPI()

class ObjectGraspInfo(BaseModel):
    object_category: str
    object_id: str
    grasp_id: int


@app.post("/api/get-object-info", response_model=ObjectGraspInfo)
async def get_object_grasp(response: Response):
    async with annotation_lock:
        category = sample_choice(CATEGORIES, num_unannotated_category)
        if category is None:
            print("All grasps annotated!")
            response.status_code = 204
            return ObjectGraspInfo(object_category="", object_id="", grasp_id=-1)
        obj_id = sample_choice(annotated_grasps[category], key=lambda oid: num_unannotated(category, oid))
        unannotated_grasps = [grasp_id for grasp_id, annotated in annotated_grasps[category][obj_id].items() if not annotated]

    grasp_id = np.random.choice(unannotated_grasps)
    print(f"Chose {category}_{obj_id} with {num_annotations(category, obj_id)} annotations")

    return ObjectGraspInfo(
        object_category=category,
        object_id=obj_id,
        grasp_id=grasp_id
    )

@app.get("/api/get-mesh-data/{category}/{obj_id}/{grasp_id}", responses={200: {"content": {"model/gltf-binary": {}}}}, response_class=Response)
async def get_mesh_data(category: str, obj_id: str, grasp_id: int):
    scene, T = load_object_data(category, obj_id)
    gripper_marker: trimesh.Trimesh = create_gripper_marker(color=[0, 255, 0]).apply_transform(T[grasp_id])
    gripper_marker.apply_translation(-scene.centroid)
    scene.apply_translation(-scene.centroid)
    scene.add_geometry(gripper_marker)

    glb_bytes = io.BytesIO()
    scene.export(glb_bytes, file_type="glb")
    return Response(content=glb_bytes.getvalue(), media_type="model/gltf-binary")

@app.post("/api/submit-annotation")
async def submit_annotation(annotation: Annotation):
    async with annotation_lock:
        total_annotations = sum(map(num_annotations_category, annotated_grasps.keys()))
    category = annotation.obj.object_category
    obj_id = annotation.obj.object_id
    grasp_id = annotation.grasp_id
    user_id = annotation.user_id
    print(f"User {user_id} annotated: {category}_{obj_id}, grasp {grasp_id}. Total annotations: {total_annotations+1}")

    annotated_grasps[category][obj_id][grasp_id] = True
    annotation_key = f"{ANNOTATION_PREFIX}{category}__{obj_id}__{grasp_id}__{user_id}.json"
    annot_bytes = io.BytesIO(annotation.model_dump_json().encode("utf-8"))
    s3.upload_fileobj(annot_bytes, BUCKET_NAME, annotation_key)


app.mount("/static", StaticFiles(directory="data_annotation/build/static"), name="static")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        # Let the API routes handle API requests
        raise HTTPException(status_code=404)
    return FileResponse(
        "data_annotation/build/index.html",
        headers={"Cache-Control": "no-cache"}
    )
