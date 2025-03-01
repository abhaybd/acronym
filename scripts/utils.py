from types_boto3_s3.client import S3Client

def list_s3_files(s3: S3Client, bucket_name: str, prefix: str):
    files_to_download: list[str] = []
    continuation_token = None
    while True:
        list_kwargs = {"Bucket": bucket_name, "Prefix": prefix}
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
