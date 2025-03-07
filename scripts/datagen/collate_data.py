import argparse
import os
import yaml
import glob
import csv

from tqdm import tqdm

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("observation_dir", type=str)
    parser.add_argument("dataset_path", type=str)
    return parser.parse_args()

def main():
    args = get_args()

    with open(args.dataset_path, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["annotation_id", "text", "observation_path"])  # Write header
        
        for annotation_path in tqdm(glob.glob(os.path.join(args.observation_dir, "**/annot.yaml"), recursive=True)):
            with open(annotation_path, "r") as f:
                annotation = yaml.safe_load(f)

            annot_id = annotation["annotation_id"]
            annot_desc = annotation["annotation"]
            data_path = os.path.relpath(annotation_path.replace("annot.yaml", "obs.pkl"), args.observation_dir)
            assert os.path.isfile(os.path.join(args.observation_dir, data_path)), f"File {data_path} does not exist"

            writer.writerow([annot_id, annot_desc, data_path])

if __name__ == "__main__":
    main()
