import argparse
import os
import shutil
import re
import pickle

import h5py
import numpy as np
from tqdm import tqdm
from scipy.spatial.transform import Rotation as R

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("grasps_root")
    parser.add_argument("shapenet_root")
    parser.add_argument("output_dir")
    parser.add_argument("--n-grasps", type=int, default=16)
    return parser.parse_args()


def rot_distance(rot_deltas: np.ndarray):
    return R.from_matrix(rot_deltas).magnitude()


def grasp_dist(grasp: np.ndarray, grasps2: np.ndarray):
    assert grasp.ndim == 2
    if grasps2.ndim == 2:
        grasps2 = grasps2[None]
    pos_dist = np.linalg.norm(grasp[None, :3, 3] - grasps2[:, :3, 3], axis=1)

    rd1 = rot_distance(grasps2[:, :3, :3].transpose(0,2,1) @ grasp[None, :3, :3])
    rd2 = rot_distance(grasps2[:, :3, :3].transpose(0,2,1) @ grasp[None, :3, :3] @ R.from_euler("z", [np.pi]).as_matrix())
    rot_dist = np.minimum(rd1, rd2)

    return pos_dist + 0.05 * rot_dist


def subsample_grasps(successes: np.ndarray, grasps: np.ndarray, n: int):
    succ_grasp_idxs = np.argwhere(successes == 1).flatten()
    grasps = grasps[succ_grasp_idxs]
    if len(grasps) <= n:
        return succ_grasp_idxs

    points_left = np.arange(len(grasps))
    sample_inds = np.zeros(n, dtype=int)
    dists = np.full_like(points_left, np.inf, dtype=float)

    selected = 0
    sample_inds[0] = selected
    points_left = np.delete(points_left, selected)

    for i in range(1, n):
        last_added_idx = sample_inds[i-1]
        dists_to_last_added = grasp_dist(grasps[last_added_idx], grasps[points_left])
        dists[points_left] = np.minimum(dists[points_left], dists_to_last_added)
        selected = np.argmax(dists[points_left])
        sample_inds[i] = points_left[selected]
        points_left = np.delete(points_left, selected)
    
    return succ_grasp_idxs[sample_inds]


def main():
    args = get_args()

    output_mesh_dir = os.path.join(args.output_dir, "meshes")
    output_grasp_dir = os.path.join(args.output_dir, "grasps")
    os.makedirs(output_mesh_dir, exist_ok=True)
    os.makedirs(output_grasp_dir, exist_ok=True)

    # maps (category, object_id, grasp_id) -> whether the grasp is annotated
    annotation_skeleton: dict[str, dict[str, dict[int, bool]]] = {}

    for grasp_filename in tqdm(os.listdir(args.grasps_root)):
        category, obj_id = grasp_filename.split("_", 1)
        obj_id = obj_id[:-len(".h5")]
        mesh_src_dir = os.path.join(args.shapenet_root, "models-OBJ", "models")
        mesh_dst_dir = os.path.join(output_mesh_dir, category)
        os.makedirs(mesh_dst_dir, exist_ok=True)

        shutil.copy2(
            os.path.join(args.grasps_root, grasp_filename),
            os.path.join(output_grasp_dir, grasp_filename)
        )
        with h5py.File(os.path.join(output_grasp_dir, grasp_filename), "r+") as f:
            _, c, mesh_fn = f["object/file"][()].decode("utf-8").split("/")
            assert c == category
            mesh_id = mesh_fn[:-len(".obj")]
            grasps = np.array(f["grasps/transforms"])
            successes = np.array(f["grasps/qualities/flex/object_in_gripper"])
            sampled_grasp_idxs = subsample_grasps(successes, grasps, args.n_grasps)
            f["grasps/sampled_idxs"] = sampled_grasp_idxs

            if category not in annotation_skeleton:
                annotation_skeleton[category] = {}
            annotation_skeleton[category][obj_id] = {i.item(): False for i in sampled_grasp_idxs}
        
        shutil.copy2(
            os.path.join(mesh_src_dir, f"{mesh_id}.obj"),
            os.path.join(mesh_dst_dir, f"{mesh_id}.obj")
        )

        texture_files = set()
        with open(os.path.join(mesh_src_dir, f"{mesh_id}.mtl"), "r") as mtl_f:
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
        with open(os.path.join(mesh_dst_dir, f"{mesh_id}.mtl"), "w") as mtl_f:
            mtl_f.write("\n".join(mtl_lines))

        for texture_file in texture_files:
            shutil.copy2(
                os.path.join(args.shapenet_root, "models-textures", "textures", texture_file),
                os.path.join(mesh_dst_dir, texture_file)
            )

    with open(os.path.join(args.output_dir, "annotation_skeleton.pkl"), "wb") as f:
        pickle.dump(annotation_skeleton, f)

if __name__ == "__main__":
    main()
