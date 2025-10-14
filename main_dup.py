import json
import os
import time


JOB_MESSAGE = os.environ.get("JOB_MESSAGE")


def main() -> None:
    if JOB_MESSAGE is None:
        print("No JOB_MESSAGE provided. Exiting without work.")
        return

    try:
        parsed = json.loads(JOB_MESSAGE)
    except (TypeError, json.JSONDecodeError):
        parsed = JOB_MESSAGE

    print("Processing message:", parsed)
    time.sleep(60)
    print("Finished processing message. Exiting.")


if __name__ == "__main__":
    main()
