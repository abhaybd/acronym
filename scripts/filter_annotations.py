import os
import random

from openai import OpenAI

from annotation import Annotation

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

class OpenAIAnnotationFilter:
    def __init__(self):
        self.client = OpenAI()

    def is_annot_good(self, task: str, annotation: Annotation) -> bool:
        messages = [
            {
                "role": "developer",
                "content": SYS_PROMPT
            },
            {
                "role": "user",
                "content": f"Here is a grasp description: \"{annotation.grasp_description}\"",
            }
        ]
        completion = self.client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=messages,
        )
        response = completion.choices[0].message.content
        print(response)
        return response.split("\n")[-1].strip().lower() == "good"

annot_filter = OpenAIAnnotationFilter()

random_annot_fn = random.choice(os.listdir("annotations"))
with open(f"annotations/{random_annot_fn}", "r") as f:
    annotation = Annotation.model_validate_json(f.read())
    print(f"Annotation from user {annotation.user_id}")
    print(f"\tObject: {annotation.obj.object_category}_{annotation.obj.object_id}")
    print(f"\tGrasp ID: {annotation.grasp_id}")
    print(f"\tLabel: {annotation.grasp_label}")
    print(f"\tMesh Malformed: {annotation.is_mesh_malformed}")
    print(f"\tTime taken: {annotation.time_taken:.2f} sec")
    print(f"\tObject Description: {annotation.obj_description}")
    print(f"\tGrasp Description: {annotation.grasp_description}")
    print(f"Is annotation good? {annot_filter.is_annot_good('filter', annotation)}")

# TODO: download annotations from S3, then filter them
