import argparse
import random

import pickle

def get_args():
    args = argparse.ArgumentParser()
    args.add_argument("--url", default="http://localhost:3000")
    args.add_argument("-p", "--prolific-code")
    args.add_argument("-o", "--output")
    args.add_argument("categories", nargs="+")
    return args.parse_args()

def main():
    args = get_args()

    with open("data/annotation_skeleton.pkl", "rb") as f:
        skeleton = pickle.load(f)

    urls = []
    for category in args.categories:
        for obj_id, grasps in skeleton[category].items():
            for grasp_id in grasps:
                url = f"{args.url}/?object_category={category}&object_id={obj_id}&grasp_id={grasp_id}"
                if args.prolific_code:
                    url += f"&prolific_code={args.prolific_code}"
                else:
                    url += "&oneshot=true"
                urls.append(url)
    random.shuffle(urls)

    if args.output:
        with open(args.output, "w") as f:
            for url in urls:
                f.write(url + "\n")
    else:
        for url in urls:
            print(url)

if __name__ == "__main__":
    main()
