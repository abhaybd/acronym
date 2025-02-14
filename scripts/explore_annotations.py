import os
import json
from tempfile import TemporaryDirectory
import re

import h5py
import boto3
import matplotlib.pyplot as plt
import trimesh
import numpy as np
from tqdm import tqdm

from acronym_tools import create_gripper_marker
from annotation import Annotation, GraspLabel

s3 = boto3.client("s3")
BUCKET_NAME = "prior-datasets"
DATA_PREFIX = "semantic-grasping/acronym/"
ANNOTATION_PREFIX = "semantic-grasping/annotations/"
LOCAL_ANNOTATION_DIR = "annotations/"

def download_annotations():
    if not os.path.exists(LOCAL_ANNOTATION_DIR):
        os.makedirs(LOCAL_ANNOTATION_DIR)

    files_to_download = []
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
                    local_path = os.path.join(LOCAL_ANNOTATION_DIR, os.path.basename(key))
                    if not os.path.exists(local_path):
                        files_to_download.append((key, local_path))

        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
        else:
            break

    for key, local_path in tqdm(files_to_download, desc="Downloading annotations", disable=len(files_to_download) == 0):
        s3.download_file(BUCKET_NAME, key, local_path)

def process_annotations():
    annotations = []
    for filename in os.listdir(LOCAL_ANNOTATION_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(LOCAL_ANNOTATION_DIR, filename), "r") as f:
                data = json.load(f)
                if "is_grasp_invalid" in data:
                    data["grasp_label"] = GraspLabel.INFEASIBLE if data["is_grasp_invalid"] else GraspLabel.BAD
                    del data["is_grasp_invalid"]
                data = Annotation(**data)
                annotations.append(data)
    return annotations

def plot_time_taken_histogram(annotations):
    times = [annotation.time_taken / 60 for annotation in annotations if annotation.time_taken >= 0]
    plt.hist(times, bins=20)
    plt.xlabel("Time Taken (min)")
    plt.ylabel("Frequency")
    plt.title("Time Taken for Annotations")
    
    median_time = np.median(times)
    plt.axvline(median_time, color='r', linestyle='dashed', linewidth=1, label=f'Median: {median_time:.2f} min')
    
    plt.legend()
    plt.show()

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

def visualize_annotation(annotation: Annotation):
    print(f"Annotation from user {annotation.user_id}")
    print(f"\tObject: {annotation.obj.object_category}_{annotation.obj.object_id}")
    print(f"\tGrasp ID: {annotation.grasp_id}")
    print(f"\tLabel: {annotation.grasp_label}")
    print(f"\tMesh Malformed: {annotation.is_mesh_malformed}")
    print(f"\tTime taken: {annotation.time_taken:.2f} sec")
    print(f"\tDescription: {annotation.description}")

    load_object_data(annotation.obj.object_category, annotation.obj.object_id)

    scene, T = load_object_data(annotation.obj.object_category, annotation.obj.object_id)
    gripper_marker = create_gripper_marker(color=[0, 255, 0]).apply_transform(T[annotation.grasp_id])
    gripper_marker.apply_translation(-scene.centroid)
    scene.apply_translation(-scene.centroid)
    scene.add_geometry(gripper_marker)
    scene.to_mesh().show()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Explore and visualize annotations.")
    parser.add_argument("--plot", action="store_true", help="Plot histogram of time taken.")
    parser.add_argument("-v", "--visualize", nargs=3, metavar=("CATEGORY", "OBJ_ID", "GRASP_ID"), help="Visualize a specific observation.")
    parser.add_argument("-r", "--random-viz", action="store_true", help="Visualize a random observation.")
    args = parser.parse_args()

    download_annotations()

    annotations = process_annotations()

    print(f"Loaded {len(annotations)} annotations.")

    if args.plot:
        plot_time_taken_histogram(annotations)

    if args.visualize:
        category, obj_id, grasp_id = args.visualize
        annot = next((a for a in annotations if a.obj.object_category == category and a.obj.object_id == obj_id and a.grasp_id == int(grasp_id)), None)
        visualize_annotation(annot)

    if args.random_viz:
        annotation: Annotation = np.random.choice(annotations)
        visualize_annotation(annotation)
