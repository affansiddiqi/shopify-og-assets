#!/usr/bin/env python3
"""Publish approved, due Instagram Reels for @shopifyog."""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
QUEUE_PATH = os.path.join(HERE, "queue.json")

PAGE_TOKEN = os.environ.get("IG_PAGE_ACCESS_TOKEN", "").strip()
IG_ACCOUNT_ID = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "").strip()
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", CONFIG.get("max_per_run", 1)))
KEEP_VIDEOS = int(os.environ.get("KEEP_VIDEOS", CONFIG.get("keep_posted_videos", 0)))

PUBLIC_BASE = CONFIG["public_assets_base"].rstrip("/")
GRAPH = "https://graph.facebook.com/v25.0"
POLL_ATTEMPTS = 40
POLL_DELAY = 5


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def is_due(item):
    when = item.get("scheduled_at")
    if not when:
        return False
    try:
        scheduled = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return scheduled.replace(tzinfo=datetime.timezone.utc) <= now_utc()


def post_form(url, data):
    request = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(), method="POST"
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def get_json(url, params):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params)) as response:
        return json.load(response)


def publish(item):
    video_url = PUBLIC_BASE + "/" + item["video"].lstrip("/")
    container = post_form(
        f"{GRAPH}/{IG_ACCOUNT_ID}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": item.get("caption", ""),
            "share_to_feed": "true",
            "access_token": PAGE_TOKEN,
        },
    )
    container_id = container["id"]

    for _ in range(POLL_ATTEMPTS):
        status = get_json(
            f"{GRAPH}/{container_id}",
            {"fields": "status_code,status", "access_token": PAGE_TOKEN},
        )
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram could not process the video: {status}")
        time.sleep(POLL_DELAY)
    else:
        raise RuntimeError("Timed out waiting for Instagram to process the video")

    return post_form(
        f"{GRAPH}/{IG_ACCOUNT_ID}/media_publish",
        {"creation_id": container_id, "access_token": PAGE_TOKEN},
    )["id"]


def cleanup_videos(queue):
    posted = [
        item
        for item in queue
        if item.get("result") == "posted" and not item.get("video_deleted")
    ]
    posted.sort(key=lambda item: item.get("posted_at_utc") or "")
    stale = posted[:-KEEP_VIDEOS] if KEEP_VIDEOS else posted

    for item in stale:
        path = os.path.join(HERE, item.get("video", ""))
        if item.get("video") and os.path.exists(path):
            os.remove(path)
        item["video_deleted"] = True
    return bool(stale)


def main():
    if not PAGE_TOKEN or not IG_ACCOUNT_ID:
        print("Instagram credentials not set. Nothing to do.")
        return

    with open(QUEUE_PATH, encoding="utf-8") as queue_file:
        queue = json.load(queue_file)

    changed = False
    posted = 0
    auth_failed = False

    for item in sorted(queue, key=lambda entry: entry.get("scheduled_at") or ""):
        if posted >= MAX_PER_RUN:
            break
        if item.get("status") != "approved" or item.get("result") == "posted":
            continue
        if not is_due(item) or not item.get("video"):
            continue
        try:
            media_id = publish(item)
            item.update(
                {
                    "result": "posted",
                    "post_id": media_id,
                    "posted_at_utc": now_utc().strftime("%Y-%m-%d %H:%M:%S"),
                    "error": None,
                }
            )
            posted += 1
            changed = True
            print(f"POSTED {item.get('id')} -> {media_id}")
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            item.update({"result": "failed", "error": f"HTTP {error.code}: {body[:500]}"})
            changed = True
            auth_failed = error.code in (190, 400, 401, 403)
            print(f"::error::{item.get('id')} failed: HTTP {error.code} {body[:300]}")

    if cleanup_videos(queue):
        changed = True
    if changed:
        with open(QUEUE_PATH, "w", encoding="utf-8") as queue_file:
            json.dump(queue, queue_file, indent=2, ensure_ascii=False)
            queue_file.write("\n")

    pending = sum(
        1
        for item in queue
        if item.get("status") == "approved" and item.get("result") != "posted"
    )
    print(f"Done. Posted {posted}. {pending} still queued.")
    if auth_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
