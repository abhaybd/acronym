import argparse
import os
import random
import io
import boto3
import base64
import urllib.parse
import json

import pickle

from types_boto3_s3 import S3Client

from utils import list_s3_files

BUCKET_NAME = "prior-datasets"
DATA_PREFIX = "semantic-grasping/acronym/"
FILTERED_ANNOT_PREFIX = "semantic-grasping/annotations-filtered/"

def get_args():
    args = argparse.ArgumentParser()
    args.add_argument("--url", default="http://localhost:3000")
    args.add_argument("-p", "--prolific-code")
    args.add_argument("-r", "--prolific-rejection-code")
    args.add_argument("-o", "--output")
    args.add_argument("--schedule-length", type=int, default=5)
    args.add_argument("--limit", type=int)
    args.add_argument("--blacklist", help="File containing object assets to blacklist")
    args.add_argument("categories", nargs="+")
    return args.parse_args()

def completed_annotations(s3: S3Client):
    ret: set[tuple[str, str, int]] = set()
    keys = list_s3_files(s3, BUCKET_NAME, FILTERED_ANNOT_PREFIX)
    for key in keys:
        filename = os.path.basename(key)[:-len(".json")]
        object_category, object_id, grasp_id, _ = filename.split("__")
        ret.add((object_category, object_id, grasp_id))
    return ret

def main():
    args = get_args()

    skeleton_bytes = io.BytesIO()
    s3 = boto3.client("s3")
    s3.download_fileobj(BUCKET_NAME, f"{DATA_PREFIX}annotation_skeleton.pkl", skeleton_bytes)
    skeleton_bytes.seek(0)
    skeleton: dict[str, dict[str, dict[int, bool]]] = pickle.load(skeleton_bytes)

    completed = completed_annotations(s3)

    if args.blacklist:
        with open(args.blacklist, "r") as f:
            blacklist = set(f.read().strip().splitlines())
    else:
        blacklist = set()

    params = []
    for category in args.categories:
        for obj_id, grasps in skeleton[category].items():
            for grasp_id in grasps:
                if (category, obj_id, grasp_id) in completed or f"{category}_{obj_id}_{grasp_id}" in blacklist:
                    continue
                p = {
                    "object_category": category,
                    "object_id": obj_id,
                    "grasp_id": grasp_id
                }
                params.append(p)
    random.shuffle(params)
    if args.limit:
        params = params[:args.limit * args.schedule_length]

    urls = []
    for i in range(0, len(params), args.schedule_length):
        schedule_items = params[i:i+args.schedule_length]
        schedule = {
            "idx": 0,
            "annotations": schedule_items
        }
        schedule_encoded = urllib.parse.quote_plus(base64.b64encode(json.dumps(schedule).encode()).decode())
        url = f"{args.url}?annotation_schedule={schedule_encoded}"
        if args.prolific_code:
            url += f"&prolific_code={args.prolific_code}"
            if args.prolific_rejection_code:
                url += f"&prolific_rejection_code={args.prolific_rejection_code}"
        else:
            url += "&oneshot=true"
        urls.append(url)

    if args.output:
        with open(args.output, "w") as f:
            for url in urls:
                f.write(url + "\n")
    else:
        for url in urls:
            print(url)

if __name__ == "__main__":
    main()
