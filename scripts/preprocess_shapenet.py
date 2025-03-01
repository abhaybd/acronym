import argparse
from collections import defaultdict
import os
import shutil
import re
import pickle

import h5py
from tqdm import tqdm

from subsample_grasps import sample_grasps, load_aligned_meshes_and_grasps

GRIPPER_POS_OFFSET = 0.075


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("grasps_root")
    parser.add_argument("shapenet_root")
    parser.add_argument("output_dir")
    parser.add_argument("--blacklist", help="File containing object assets to blacklist")
    parser.add_argument("--n-proc", type=int, default=16, help="Number of processes to use")
    parser.add_argument("--n-grasps", type=int, default=4, help="Minimum number of grasps per object instance in a category")
    parser.add_argument("--min-grasps", type=int, default=32, help="Minimum number of grasps per category")
    parser.add_argument("--only-sample-grasps", action="store_true", help="Only sample grasps, do not copy meshes")
    parser.add_argument("--sampling-categories-file", help="File containing categories to resample grasps for")
    return parser.parse_args()


def copy_assets(args):
    output_mesh_dir = os.path.join(args.output_dir, "meshes")
    output_grasp_dir = os.path.join(args.output_dir, "grasps")
    os.makedirs(output_mesh_dir, exist_ok=True)
    os.makedirs(output_grasp_dir, exist_ok=True)

    if args.blacklist:
        with open(args.blacklist, "r") as f:
            blacklist = set(f.read().strip().splitlines())
    else:
        blacklist = set()

    for grasp_filename in tqdm(os.listdir(args.grasps_root)):
        if grasp_filename[:-len(".h5")] in blacklist:
            continue
        category = grasp_filename.split("_", 1)[0]
        mesh_src_dir = os.path.join(args.shapenet_root, "models-OBJ", "models")
        mesh_dst_dir = os.path.join(output_mesh_dir, category)
        os.makedirs(mesh_dst_dir, exist_ok=True)

        shutil.copy2(
            os.path.join(args.grasps_root, grasp_filename),
            os.path.join(output_grasp_dir, grasp_filename)
        )
        with h5py.File(os.path.join(output_grasp_dir, grasp_filename), "r") as f:
            _, c, mesh_fn = f["object/file"][()].decode("utf-8").split("/")
            assert c == category
            mesh_id = mesh_fn[:-len(".obj")]
        
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
                elif m := re.fullmatch(r"Kd 0(?:.0)? 0(?:.0)? 0(?:.0)?", line):
                    mtl_lines.append("Kd 1 1 1")
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


def subsample_grasps(args):
    # maps (category, object_id, grasp_id) -> whether the grasp is annotated
    annotation_skeleton: dict[str, dict[str, dict[int, bool]]] = {}
    output_grasp_dir = os.path.join(args.output_dir, "grasps")

    category_objects: dict[str, list[str]] = defaultdict(list)
    for grasp_filename in os.listdir(output_grasp_dir):
        category, obj_id = grasp_filename.split("_", 1)
        obj_id = obj_id[:-len(".h5")]
        category_objects[category].append(obj_id)

    if args.sampling_categories_file:
        with open(args.sampling_categories_file, "r") as f:
            sampling_categories = f.read().splitlines()
    else:
        sampling_categories = sorted(category_objects.keys())

    for category in tqdm(sampling_categories, desc="Subsampling grasps"):
        obj_ids = category_objects[category]
        _, grasps, succs = load_aligned_meshes_and_grasps(category, obj_ids, args.n_proc)
        n_grasps = max(args.n_grasps * len(obj_ids), args.min_grasps)
        grasp_idxs_per_obj = sample_grasps(grasps, succs, n_grasps)
        for obj_id, grasp_idxs in zip(obj_ids, grasp_idxs_per_obj):
            grasp_filename = f"{category}_{obj_id}.h5"
            with h5py.File(os.path.join(output_grasp_dir, grasp_filename), "r+") as f:
                if "grasps/sampled_idxs" in f:
                    del f["grasps/sampled_idxs"]
                f["grasps/sampled_idxs"] = grasp_idxs

            if category not in annotation_skeleton:
                annotation_skeleton[category] = {}
            annotation_skeleton[category][obj_id] = {i.item(): False for i in grasp_idxs}

    with open(os.path.join(args.output_dir, "annotation_skeleton.pkl"), "wb") as f:
        pickle.dump(annotation_skeleton, f)

def main():
    args = get_args()

    if not args.only_sample_grasps:
        copy_assets(args)
    subsample_grasps(args)

if __name__ == "__main__":
    main()
