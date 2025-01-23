import argparse
import csv
import os
import shutil
import re

import h5py
from tqdm import tqdm

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("grasps_root")
    parser.add_argument("shapenet_root")
    parser.add_argument("output_dir")
    return parser.parse_args()

def main():
    args = get_args()

    object_categories = {}
    for grasp_filename in tqdm(os.listdir(args.grasps_root), desc="Compiling object categories"):
        with h5py.File(os.path.join(args.grasps_root, grasp_filename), "r") as f:
            _, category, mesh_fn = f["object/file"][()].decode("utf-8").split("/")
            obj_id = mesh_fn.split(".")[0]
            object_categories[obj_id] = category

    os.makedirs(args.output_dir, exist_ok=True)
    with open(os.path.join(args.shapenet_root, "metadata.csv"), "r") as f:
        n_rows = sum(1 for _ in f)
        f.seek(0)
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="Copying meshes", total=n_rows):
            obj_id = row["fullId"].split(".", 1)[1]
            categories = row["category"]
            if obj_id in object_categories and object_categories[obj_id] in categories:
                category_dir = os.path.join(args.output_dir, object_categories[obj_id])
                os.makedirs(category_dir, exist_ok=True)
                shutil.copy2(os.path.join(args.shapenet_root, "models-OBJ", "models", f"{obj_id}.obj"), os.path.join(category_dir, f"{obj_id}.obj"))

                # TODO: also copy referenced texture images
                with open(os.path.join(args.shapenet_root, "models-OBJ", "models", f"{obj_id}.mtl"), "r") as mtl_f:
                    mtl_lines = []
                    for line in mtl_f:
                        line = line.strip()
                        m = re.fullmatch(r"d (\d+\.?\d*)", line)
                        if m:
                            mtl_lines.append(f"d {1-float(m.group(1))}")
                        else:
                            mtl_lines.append(line)
                with open(os.path.join(category_dir, f"{obj_id}.mtl"), "w") as mtl_f:
                    mtl_f.write("\n".join(mtl_lines))

if __name__ == "__main__":
    main()
