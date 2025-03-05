import json
import os
import re
import argparse
import time
from pydantic import BaseModel
import requests
from tqdm import tqdm
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import compress

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
import boto3
from types_boto3_s3.client import S3Client

from annotation import Annotation, GraspLabel
from utils import list_s3_files


BUCKET_NAME = "prior-datasets"
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
Given a grasp description, analyze it according to the guidelines. Respond with a short explanation of whether it follows the rules, followed by a judgement of whether the description is good or bad. If the description is almost good, try to revise it to adhere to the guidelines which keeping the content unchanged. If the description is sufficiently bad or does not provide enough detail, do not attempt to revise it.
""".strip()

class DescriptionJudgement(BaseModel):
    explanation: str
    is_good: bool
    revised_description: str | None

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--retrieve", nargs="?", const="", help="The batch ID to retrieve results for, provide flag without value when used with --submit")
    parser.add_argument("--overwrite", action="store_true", help="Reprocess annotations even if they already exist in the destination directory")
    parser.add_argument("--src-prefix", default="semantic-grasping/annotations/", help="The prefix of the source annotations")
    parser.add_argument("--dst-prefix", default="semantic-grasping/annotations-filtered/", help="The prefix of the destination annotations")
    parser.add_argument("--study", help="The study to filter annotations for")
    return parser

def get_annot_details(s3: S3Client, pfx: str):
    annot_file = BytesIO()
    s3.download_fileobj(BUCKET_NAME, pfx, annot_file)
    annot_file.seek(0)
    annot = Annotation.model_validate_json(annot_file.read())
    return pfx, annot

def prefilter_annotation(annot: Annotation):
    return annot.grasp_label != GraspLabel.INFEASIBLE

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
            "max_tokens": 8192,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "description_judgement",
                    "strict": True,
                    "schema": to_strict_json_schema(DescriptionJudgement)
                }
            }
        }
    }

def submit_job(openai: OpenAI, s3: S3Client, overwrite: bool, src_prefix: str, dst_prefix: str, users: set[str] | None = None):
    unannotated_pfxs = list_s3_files(s3, BUCKET_NAME, src_prefix)
    if not overwrite:
        annotated_pfxs = set(list_s3_files(s3, BUCKET_NAME, dst_prefix))
        unannotated_pfxs = [pfx for pfx in unannotated_pfxs if pfx not in annotated_pfxs]

    annot_pfxs: list[str] = []
    annots: list[Annotation] = []
    n_unfiltered = len(unannotated_pfxs)
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(get_annot_details, s3, pfx) for pfx in unannotated_pfxs]
        for future in tqdm(as_completed(futures), total=len(futures), dynamic_ncols=True, desc="Fetching annotations"):
            pfx, annot = future.result()
            annot_pfxs.append(pfx)
            if users is None or annot.user_id in users:
                annots.append(annot)

    prefiltered_mask = list(map(prefilter_annotation, annots))
    annot_pfxs = list(compress(annot_pfxs, prefiltered_mask))
    annots = list(compress(annots, prefiltered_mask))

    print(f"Prefiltering yield: {len(annot_pfxs)}/{n_unfiltered} ({len(annot_pfxs) / n_unfiltered:.0%})")

    batch_file = BytesIO()
    for pfx, annot in zip(annot_pfxs, annots):
        query = generate_query(pfx, annot)
        batch_file.write((json.dumps(query) + "\n").encode("utf-8"))
    batch_file.seek(0)
    batch_file_id = openai.files.create(file=batch_file, purpose="batch").id
    batch = openai.batches.create(input_file_id=batch_file_id, endpoint="/v1/chat/completions", completion_window="24h")
    print(f"Submitted batch job with id: {batch.id}")
    return batch.id, batch_file_id

def retrieve_job(openai: OpenAI, s3: S3Client, batch_id: str, batch_file_id: str | None, src_prefix: str, dst_prefix: str):
    done_statuses = ["completed", "expired", "cancelled", "failed"]
    while (batch := openai.batches.retrieve(batch_id)).status not in done_statuses:
        time.sleep(10)
    if batch.status != "completed":
        print(f"Batch job {batch_id} did not complete successfully!")
        return
    batch_file = openai.files.content(batch.output_file_id)

    valid_annot_pfxs = []
    revisions = []
    batch_file_lines = batch_file.content.decode("utf-8").splitlines()
    for line in batch_file_lines:
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            print(f"Malformed JSON response: {line}")
            continue
        pfx = result["custom_id"]
        response = DescriptionJudgement.model_validate_json(result["response"]["body"]["choices"][0]["message"]["content"])
        annot_desc = get_annot_details(s3, pfx)[1].grasp_description
        print("Judgement:", "Good" if response.is_good else "Bad", "-> Good" if response.revised_description else "")
        print("Annotation:", re.sub(r"\n+", " ", annot_desc))
        print("Response:", re.sub(r"\n+", " ", response.explanation))
        if response.revised_description:
            print("Revised:", response.revised_description)
        print("-"*100 + "\n")
        if response.is_good:
            valid_annot_pfxs.append(pfx)
        elif response.revised_description:
            revisions.append((pfx, response.revised_description))

    for pfx in tqdm(valid_annot_pfxs, desc="Copying valid annotations"):
        bn = os.path.basename(pfx)
        s3.copy_object(CopySource=f"{BUCKET_NAME}/{src_prefix}{bn}",
                       Bucket=BUCKET_NAME, Key=f"{dst_prefix}{bn}")

    for pfx, revised_desc in tqdm(revisions, desc="Revising annotations"):
        annot = get_annot_details(s3, pfx)[1]
        annot = annot.model_copy(update={"grasp_description": revised_desc})
        annot_file = BytesIO(annot.model_dump_json().encode("utf-8"))
        annot_file.seek(0)
        bn = os.path.basename(pfx)
        s3.upload_fileobj(annot_file, BUCKET_NAME, f"{dst_prefix}{bn}")

    n_unfiltered = len(batch_file_lines)
    print(f"Filtering yield: {len(valid_annot_pfxs)}/{n_unfiltered} ({len(valid_annot_pfxs) / n_unfiltered:.0%})")
    print(f"After revisions: {len(revisions)+len(valid_annot_pfxs)}/{n_unfiltered} ({(len(revisions)+len(valid_annot_pfxs)) / n_unfiltered:.0%})")

    if batch_file_id:
        openai.files.delete(batch_file_id)

def main():
    parser = get_parser()
    args = parser.parse_args()
    if not args.submit and not args.retrieve:
        parser.print_usage()
        return
    if args.submit and args.retrieve is not None and len(args.retrieve) > 0:
        parser.error("If submitting and retrieving, do not provide a batch ID")

    openai = OpenAI()
    s3 = boto3.client("s3")

    if args.submit:
        if args.study:
            token = os.getenv("PROLIFIC_TOKEN")
            assert token is not None, "PROLIFIC_TOKEN is not set"
            response = requests.get(
                "https://api.prolific.com/api/v1/submissions/",
                headers={"Authorization": f"Token {token}"},
                params={"study": args.study}
            )
            if response.ok:
                submissions = response.json()
                users = set()
                for submission in submissions["results"]:
                    if submission["status"] == "APPROVED":
                        users.add(submission["participant_id"])
            else:
                raise Exception(f"Failed to retrieve submissions: {response.status_code} {response.text}")
        else:
            users = None
        batch_id, batch_file_id = submit_job(openai, s3, args.overwrite, args.src_prefix, args.dst_prefix, users)
    else:
        batch_id = args.retrieve
        batch_file_id = None

    if args.retrieve is not None:
        retrieve_job(openai, s3, batch_id, batch_file_id, args.src_prefix, args.dst_prefix)

if __name__ == "__main__":
    main()
