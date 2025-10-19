import boto3

# S3 configuration
bucket_name = "highlight-clipping-service-main-975049899047"
base_path = "streams/"  # Only folders under this path will be considered
dontdelete = ["mediaconvert_input/",]  # relative to base_path

s3 = boto3.resource("s3")
bucket = s3.Bucket(bucket_name)

# Gather all first-level folders under base_path
folders = set()
for obj in bucket.objects.filter(Prefix=base_path):
    key = obj.key
    # Skip the base_path itself
    if key == base_path:
        continue
    # Extract first-level folder under base_path
    relative_path = key[len(base_path):]
    if "/" in relative_path:
        folder = relative_path.split("/")[0] + "/"
        folders.add(folder)

# Delete folders not in dontdelete
for folder in folders:
    if folder not in dontdelete:
        prefix_to_delete = base_path + folder
        print(f"Deleting folder and its contents: {prefix_to_delete}")
        bucket.objects.filter(Prefix=prefix_to_delete).delete()
    else:
        print(f"Skipping folder: {base_path + folder}")
