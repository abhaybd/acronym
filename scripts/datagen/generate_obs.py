import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from io import BytesIO
import os
import pickle
import random
import time
from base64 import b64decode
from contextlib import contextmanager
import signal

import numpy as np
from tqdm import tqdm
import pyrender
import pyrender.light
import trimesh

import datagen_utils
assert datagen_utils  # imported for modification to path
from annotation import Annotation

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str, help="Input directory")
    parser.add_argument("output_dir", type=str, help="Output directory")
    parser.add_argument("--n-proc", type=int, help="Number of processes, if unspecified uses all available cores")
    parser.add_argument("--n-scenes", type=int, help="Total number of scenes to process")
    parser.add_argument("--img-size", type=int, nargs=2, default=(480, 640),
                        help="Default image size as (height, width), for best performance this should match the generated data.")
    return parser.parse_args()

@contextmanager
def block_signals(signals: list[int]):
    previous_blocked = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    try:
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_blocked)

def worker_init(img_size: tuple[int, int]):
    height, width = img_size
    renderer = pyrender.OffscreenRenderer(width, height)
    globals()["renderer"] = renderer

def build_scene(data: dict[str, any]):
    glb_bytes = BytesIO(b64decode(data["glb"].encode("utf-8")))
    tr_scene: trimesh.Scene = trimesh.load(glb_bytes, file_type="glb")
    scene = pyrender.Scene.from_trimesh_scene(tr_scene)

    for light in data["lighting"]:
        light_type = getattr(pyrender.light, light["type"])
        light_args = light["args"]
        light_args["color"] = np.array(light_args["color"]) / 255.0
        light_node = pyrender.Node(light["args"]["name"], matrix=light["transform"], light=light_type(**light_args))
        scene.add_node(light_node)
    return scene

def set_camera(scene: pyrender.Scene, cam_K: np.ndarray, cam_pose: np.ndarray):
    cam = pyrender.camera.IntrinsicsCamera(
        fx=cam_K[0, 0],
        fy=cam_K[1, 1],
        cx=cam_K[0, 2],
        cy=cam_K[1, 2],
        name="camera",
    )
    cam_node = pyrender.Node(name="camera", camera=cam, matrix=cam_pose)
    for n in (scene.get_nodes(name=cam_node.name) or []):
        scene.remove_node(n)
    scene.add_node(cam_node)

    cam_light = pyrender.light.PointLight(intensity=2.0, name="camera_light")
    camera_light_node = pyrender.Node(name="camera_light", matrix=cam_pose, light=cam_light)
    for n in (scene.get_nodes(name=camera_light_node.name) or []):
        scene.remove_node(n)
    scene.add_node(camera_light_node)

def backproject(cam_K: np.ndarray, depth: np.ndarray):
    height, width = depth.shape
    u, v = np.meshgrid(np.arange(width), np.arange(height), indexing="xy")
    uvd = np.stack((u, v, np.ones_like(u)), axis=-1).astype(np.float32)
    uvd *= np.expand_dims(depth, axis=-1)
    xyz = uvd @ np.expand_dims(np.linalg.inv(cam_K).T, axis=0)
    return xyz

def render(out_dir: str, scene_path: str):
    # TODO: need to also save text and construct pairwise comparison matrix
    scene_id = os.path.basename(scene_path)[:-len(".pkl")]
    if os.path.exists(f"{out_dir}/{scene_id}_0_0.pkl"):
        # if one observation was generated, assume all were
        print(f"Skipping {scene_id} because it already has observations")
        return

    with open(scene_path, "rb") as f:
        scene_data = pickle.load(f)
    all_annotations: dict[str, tuple[Annotation, np.ndarray]] = scene_data["annotations"]
    scene = build_scene(scene_data)

    renderer: pyrender.OffscreenRenderer = globals()["renderer"]
    renderer.viewport_height, renderer.viewport_width = scene_data["img_size"]

    observations: list[list[bytes]] = []
    for view in scene_data["views"]:
        cam_K = np.array(view["cam_K"])
        cam_pose = np.array(view["cam_pose"])
        set_camera(scene, cam_K, cam_pose)

        color, depth = renderer.render(scene, flags=pyrender.RenderFlags.SHADOWS_DIRECTIONAL)
        xyz = backproject(cam_K, depth)

        obs_per_view = []
        for annot_id in view["annotations_in_view"]:
            _, grasp_pose = all_annotations[annot_id]
            grasp_pose_in_cam_frame = np.linalg.solve(cam_pose, grasp_pose)
            obs_data = {
                "rgb": color,
                "xyz": xyz,
                "grasp_pose": grasp_pose_in_cam_frame,
            }
            obs_per_view.append(pickle.dumps(obs_data))
        observations.append(obs_per_view)

    with block_signals([signal.SIGINT]):
        for view_idx, obs_per_view in enumerate(observations):
            for obs_idx, obs in enumerate(obs_per_view):
                out_path = f"{out_dir}/{scene_id}_{view_idx}_{obs_idx}.pkl"
                with open(out_path, "wb") as f:
                    f.write(obs)

def main():
    args = get_args()

    os.makedirs(args.output_dir, exist_ok=True)

    nproc = args.n_proc or os.cpu_count()
    with ProcessPoolExecutor(
        max_workers=nproc,
        initializer=worker_init,
        initargs=(args.img_size,)
    ) as executor:
        while True:
            scenes: set[str] = set(fn for fn in os.listdir(args.input_dir) if fn.endswith(".pkl"))
            processed_scenes: set[str] = set(fn.split("_", 1)[0] + ".pkl" for fn in os.listdir(args.output_dir) if fn.endswith(".pkl"))
            print(f"Total generated observations: {len(processed_scenes)}")

            if args.n_scenes and len(processed_scenes) >= args.n_scenes:
                print("Generated enough samples, exiting")
                break

            batch = list(scenes - processed_scenes)
            if len(batch) == 0:
                print("No new scenes, waiting...")
                time.sleep(60)
                continue
            random.shuffle(batch)  # shuffled to avoid different workers processing the same scenes
            batch = batch[:min(len(batch), 4 * nproc)]

            futures = [executor.submit(render, args.output_dir, f"{args.input_dir}/{fn}") for fn in batch]
            for f in tqdm(as_completed(futures), total=len(futures), desc="Rendering", dynamic_ncols=True):
                f.result()

if __name__ == "__main__":
    main()
