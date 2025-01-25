import argparse
import csv
import os
import shutil
import re

import h5py
import numpy as np
from tqdm import tqdm

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("grasps_root")
    parser.add_argument("shapenet_root")
    parser.add_argument("output_dir")
    parser.add_argument("--n-grasps", type=int, default=16)
    return parser.parse_args()

def subsample_grasps(successes: np.ndarray, grasps: np.ndarray, n: int):
    succ_grasp_idxs = np.argwhere(successes == 1).flatten()
    grasps = grasps[succ_grasp_idxs]
    if len(grasps) <= n:
        return succ_grasp_idxs

    points_left = np.arange(len(grasps))
    sample_inds = np.zeros(n, dtype=int)
    dists = np.full_like(points_left, np.inf, dtype=float)

    selected = np.random.choice(len(grasps))
    sample_inds[0] = selected
    points_left = np.delete(points_left, selected)

    for i in range(1, n):
        last_added_idx = sample_inds[i-1]
        dists_to_last_added = np.linalg.norm(grasps[last_added_idx] - grasps[points_left], axis=(1, 2))
        dists[points_left] = np.minimum(dists[points_left], dists_to_last_added)
        selected = np.argmax(dists[points_left])
        sample_inds[i] = points_left[selected]
        points_left = np.delete(points_left, selected)
    
    return succ_grasp_idxs[sample_inds]


def main():
    args = get_args()

    object_categories = {}
    object_datafiles = {}
    for grasp_filename in tqdm(os.listdir(args.grasps_root), desc="Compiling object categories"):
        with h5py.File(os.path.join(args.grasps_root, grasp_filename), "r") as f:
            _, category, mesh_fn = f["object/file"][()].decode("utf-8").split("/")
            obj_id = mesh_fn.split(".")[0]
            object_categories[obj_id] = category
            object_datafiles[obj_id] = grasp_filename

    output_mesh_dir = os.path.join(args.output_dir, "meshes")
    output_grasp_dir = os.path.join(args.output_dir, "grasps")
    os.makedirs(output_mesh_dir, exist_ok=True)
    os.makedirs(output_grasp_dir, exist_ok=True)

    with open(os.path.join(args.shapenet_root, "metadata.csv"), "r") as f:
        n_rows = sum(1 for _ in f)
        f.seek(0)
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="Copying meshes", total=n_rows):
            obj_id = row["fullId"].split(".", 1)[1]
            categories = row["category"]
            if obj_id in object_categories and object_categories[obj_id] in categories:
                mesh_src_dir = os.path.join(args.shapenet_root, "models-OBJ", "models")
                mesh_dst_dir = os.path.join(output_mesh_dir, object_categories[obj_id])
                os.makedirs(mesh_dst_dir, exist_ok=True)
                shutil.copy2(
                    os.path.join(mesh_src_dir, f"{obj_id}.obj"),
                    os.path.join(mesh_dst_dir, f"{obj_id}.obj")
                )

                texture_files = set()
                with open(os.path.join(mesh_src_dir, f"{obj_id}.mtl"), "r") as mtl_f:
                    mtl_lines = []
                    for line in mtl_f:
                        line = line.strip()
                        if m := re.fullmatch(r"d (\d+\.?\d*)", line):
                            mtl_lines.append(f"d {1-float(m.group(1))}")
                        elif m := re.fullmatch(r".+ (.+\.jpg)", line):
                            texture_files.add(m.group(1))
                            mtl_lines.append(line)
                        else:
                            mtl_lines.append(line)
                with open(os.path.join(mesh_dst_dir, f"{obj_id}.mtl"), "w") as mtl_f:
                    mtl_f.write("\n".join(mtl_lines))

                for texture_file in texture_files:
                    shutil.copy2(
                        os.path.join(args.shapenet_root, "models-textures", "textures", texture_file),
                        os.path.join(mesh_dst_dir, texture_file)
                    )

                shutil.copy2(
                    os.path.join(args.grasps_root, object_datafiles[obj_id]),
                    os.path.join(output_grasp_dir, object_datafiles[obj_id])
                )
                with h5py.File(os.path.join(output_grasp_dir, object_datafiles[obj_id]), "r+") as f:
                    grasps = np.array(f["grasps/transforms"])
                    successes = np.array(f["grasps/qualities/flex/object_in_gripper"])
                    sampled_grasp_idxs = subsample_grasps(successes, grasps, args.n_grasps)
                    del f["grasps/transforms"]
                    del f["grasps/qualities/flex/object_in_gripper"]
                    f["grasps/transforms"] = grasps[sampled_grasp_idxs]
                    f["grasps/qualities/flex/object_in_gripper"] = successes[sampled_grasp_idxs]

if __name__ == "__main__":
    main()
