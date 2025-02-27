import json
import os
import re
import argparse
import time
from tqdm import tqdm
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import compress

from openai import OpenAI
import boto3
from types_boto3_s3.client import S3Client

from annotation import Annotation, GraspLabel

BUCKET_NAME = "prior-datasets"
ANNOTATION_SRC_DIR = "semantic-grasping/annotations/"
ANNOTATION_DST_DIR = "semantic-grasping/annotations-filtered/"
SYS_PROMPT = """
You are an AI assistant designed to filter out improper grasp descriptions based on a set of strict guidelines. A grasp description should be a concise and detailed explanation of the grasp's position and orientation relative to an object. Your task is to determine whether a given grasp description follows the provided guidelines.

Guidelines for a Good Grasp Description:
 - The description must specify where the grasp is on the object and how it is oriented.
 - It must be neutral and factual, without making any judgments about the grasp's quality (e.g., good, bad, stable, unstable).
 - It must not suggest alternative or better grasp positions.
 - It must not refer to previous grasps or make assumptions about the intent of the grasp.

Examples of Good Grasp Descriptions:
 - "The grasp is placed on the side of the mug where it connects to the body and is parallel with the body, placed in the middle vertically."
 - "The grasp is on the spout of the teapot, where it connects to the body. The grasp is oriented parallel to the base of the teapot, and the fingers are closing on either side of the spout."

Examples of Bad Grasp Descriptions:
 - "The mug is being held from the inside of the rim as opposed to the handle." (Comparing to an alternative grasp)
 - "The grasp is on the spoon, which is fine if that's the intention, but I would assume the grasp is supposed to be on the handle of the mug." (Speculating on intent)
 - "The grasp is off and bad positioning cup will fall." (Judging grasp quality)

Your Task:
Given a grasp description, analyze it according to the guidelines. Respond with a short explanation of whether it follows the rules, followed by either "good" or "bad" in a new paragraph to clearly indicate your decision.
""".strip()

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--retrieve", nargs="?", help="The batch ID to retrieve results for, provide flag without value when used with --submit")
    parser.add_argument("--overwrite", action="store_true", help="Reprocess annotations even if they already exist in the destination directory")
    return parser

def list_s3_files(s3: S3Client, prefix: str):
    files_to_download = []
    continuation_token = None
    while True:
        list_kwargs = {"Bucket": BUCKET_NAME, "Prefix": prefix}
        if continuation_token:
            list_kwargs["ContinuationToken"] = continuation_token
        response = s3.list_objects_v2(**list_kwargs)

        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                if key.endswith(".json"):
                    files_to_download.append(key)

        if response.get("IsTruncated"):
            continuation_token = response["NextContinuationToken"]
        else:
            break
    return files_to_download

def get_annot_details(s3: S3Client, pfx: str):
    annot_file = BytesIO()
    s3.download_fileobj(BUCKET_NAME, pfx, annot_file)
    annot_file.seek(0)
    annot = Annotation.model_validate_json(annot_file.read())
    return pfx, annot

def prefilter_annotation(annot: Annotation):
    return annot.grasp_label != GraspLabel.INFEASIBLE and not annot.is_mesh_malformed

def generate_query(pfx:str, annot: Annotation):
    return {
        "custom_id": pfx,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "developer",
                    "content": SYS_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Here is a grasp description: \"{annot.grasp_description}\""
                }
            ],
            "max_tokens": 8192
        }
    }

def submit_job(openai: OpenAI, s3: S3Client, overwrite: bool):
    unannotated_pfxs = list_s3_files(s3, ANNOTATION_SRC_DIR)
    if not overwrite:
        annotated_pfxs = set(list_s3_files(s3, ANNOTATION_DST_DIR))
        unannotated_pfxs = [pfx for pfx in unannotated_pfxs if pfx not in annotated_pfxs]

    annot_pfxs: list[str] = []
    annots: list[Annotation] = []
    n_unfiltered = len(unannotated_pfxs)
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(get_annot_details, s3, pfx) for pfx in unannotated_pfxs]
        for future in tqdm(as_completed(futures), total=len(futures), dynamic_ncols=True, desc="Fetching annotations"):
            pfx, annot = future.result()
            annot_pfxs.append(pfx)
            annots.append(annot)

    prefiltered_mask = list(map(prefilter_annotation, annots))
    annot_pfxs = list(compress(annot_pfxs, prefiltered_mask))
    annots = list(compress(annots, prefiltered_mask))

    print(f"Yield after prefiltering: {len(annot_pfxs)}/{n_unfiltered} ({100*len(annot_pfxs) / n_unfiltered:.0%}%)")

    batch_file = BytesIO()
    for pfx, annot in zip(annot_pfxs, annots):
        query = generate_query(pfx, annot)
        batch_file.write((json.dumps(query) + "\n").encode("utf-8"))
    batch_file.seek(0)
    batch_file_id = openai.files.create(file=batch_file, purpose="batch").id
    batch = openai.batches.create(input_file_id=batch_file_id, endpoint="/v1/chat/completions", completion_window="24h")
    print(f"Submitted batch job with id: {batch.id}")
    return batch.id, batch_file_id

def retrieve_job(openai: OpenAI, s3: S3Client, batch_id: str, batch_file_id: str | None):
    done_statuses = ["completed", "expired", "cancelled", "failed"]
    while (batch := openai.batches.retrieve(batch_id)).status not in done_statuses:
        time.sleep(10)
    if batch.status != "completed":
        print(f"Batch job {batch_id} did not complete successfully!")
        return
    batch_file = openai.files.content(batch.output_file_id)

    valid_pfxs = []
    batch_file_lines = batch_file.content.decode("utf-8").splitlines()
    for line in batch_file_lines:
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            print(f"Malformed JSON response: {line}")
            continue
        pfx = result["custom_id"]
        response = result["response"]["body"]["choices"][0]["message"]["content"]
        annot_desc = get_annot_details(s3, pfx)[1].grasp_description
        print("Annotation:", re.sub(r"\n+", " ", annot_desc))
        print("Response:", re.sub(r"\n+", " ", response))
        print("-"*100 + "\n")
        valid = re.sub(r"[^a-z]", "", response.split("\n")[-1].strip().lower()) == "good"
        if valid:
            valid_pfxs.append(pfx)

    for pfx in tqdm(valid_pfxs, desc="Copying valid annotations"):
        bn = os.path.basename(pfx)
        s3.copy_object(CopySource=f"{BUCKET_NAME}/{ANNOTATION_SRC_DIR}{bn}",
                       Bucket=BUCKET_NAME, Key=f"{ANNOTATION_DST_DIR}{bn}")

    if batch_file_id:
        openai.files.delete(batch_file_id)

def main():
    parser = get_parser()
    args = parser.parse_args()
    if not args.submit and not args.retrieve:
        parser.print_usage()
        return
    if args.submit and args.retrieve and len(args.retrieve) > 0:
        parser.error("If submitting and retrieving, do not provide a batch ID")

    openai = OpenAI()
    s3 = boto3.client("s3")

    if args.submit:
        batch_id, batch_file_id = submit_job(openai, s3, args.overwrite)
    else:
        batch_id = args.retrieve
        batch_file_id = None

    if args.retrieve:
        retrieve_job(openai, s3, batch_id, batch_file_id)

        n_unfiltered = len(list_s3_files(s3, ANNOTATION_SRC_DIR))
        n_filtered = len(list_s3_files(s3, ANNOTATION_DST_DIR))
        print(f"Annotation yield: {n_filtered}/{n_unfiltered} ({100*n_filtered / n_unfiltered:.0f}%)")

if __name__ == "__main__":
    main()

# class OpenAIAnnotationFilter:
#     def __init__(self):
#         self.client = OpenAI()

#     def is_annot_good(self, annotation: Annotation) -> bool:
#         messages = [
#             {
#                 "role": "developer",
#                 "content": SYS_PROMPT
#             },
#             {
#                 "role": "user",
#                 "content": f"Here is a grasp description: \"{annotation.grasp_description}\"",
#             }
#         ]
#         completion = self.client.beta.chat.completions.parse(
#             model="gpt-4o",
#             messages=messages,
#         )
#         response = completion.choices[0].message.content
#         print(response)
#         return response.split("\n")[-1].strip().lower() == "good"

# annot_filter = OpenAIAnnotationFilter()

# random_annot_fn = random.choice(os.listdir("annotations"))
# with open(f"annotations/{random_annot_fn}", "r") as f:
#     annotation = Annotation.model_validate_json(f.read())
#     print(f"Annotation from user {annotation.user_id}")
#     print(f"\tObject: {annotation.obj.object_category}_{annotation.obj.object_id}")
#     print(f"\tGrasp ID: {annotation.grasp_id}")
#     print(f"\tLabel: {annotation.grasp_label}")
#     print(f"\tMesh Malformed: {annotation.is_mesh_malformed}")
#     print(f"\tTime taken: {annotation.time_taken:.2f} sec")
#     print(f"\tObject Description: {annotation.obj_description}")
#     print(f"\tGrasp Description: {annotation.grasp_description}")
#     print(f"Is annotation good? {annot_filter.is_annot_good(annotation)}")

# # TODO: download annotations from S3, then filter them
