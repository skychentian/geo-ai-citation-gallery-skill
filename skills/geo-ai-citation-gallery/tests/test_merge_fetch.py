import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_fetch.py"
ALL_FIELDS = [
    "title", "desc", "hashtags", "account", "follower_count", "digg_count",
    "collect_count", "share_count", "comment_count", "play_count", "content_type",
    "duration_sec", "video_file", "frames", "transcript", "publish_time", "cover", "images",
]


def run_merge(pkg, fetch, *extra):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-B", str(SCRIPT), "--package", str(pkg), "--fetch", str(fetch), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def dump(path, obj, trailing="\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")


def status_row(rank, vid, full=False, **overrides):
    fields = {name: {"status": "ok", "reason": ""} for name in ALL_FIELDS} if full else {}
    for key, value in overrides.items():
        if value is None:
            fields.pop(key, None)
            continue
        if isinstance(value, dict):
            fields[key] = value
        else:
            fields[key] = {"status": value, "reason": ""}
    return {"rank": rank, "video_id": vid, "fields": fields}


def write_case(root, rows, items, statuses, *, top=None, trailing="\n", kind="object", media=None):
    pkg, fetch = Path(root) / "pkg", Path(root) / "fetch"
    payload = rows if kind == "list" else {"STATS": {"meta": {"keep": 1}, "app_rate": 11.0}, "data": rows}
    data_path = pkg / "gallery" / "data.json"
    dump(data_path, payload, trailing)
    dump(fetch / "items.json", items)
    dump(fetch / "field_status.json", statuses)
    if top is not None:
        dump(pkg / "_机器可读" / "top.json", top)
    for rel, content in (media or {}).items():
        path = fetch / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return pkg, fetch, data_path.read_bytes()


def load_payload(pkg):
    return json.loads((pkg / "gallery" / "data.json").read_text(encoding="utf-8"))


def rows_of(payload):
    return payload if isinstance(payload, list) else payload["data"]


def report_of(pkg):
    folder = pkg / "work" / "merge_fetch"
    docs = sorted(folder.glob("merge-report-*.json"))
    mds = sorted(folder.glob("merge-report-*.md"))
    if len(docs) != 1 or len(mds) != 1:
        raise AssertionError(f"报告文件数量不对：json={len(docs)} md={len(mds)}")
    return json.loads(docs[0].read_text(encoding="utf-8")), mds[0].read_text(encoding="utf-8")


def base_item(**kwargs):
    item = {
        "rank": 1,
        "video_id": "100",
        "status": "ok",
        "title": "平台发布标题",
        "title_source": "itemTitle",
        "original_desc": "发布文案全文",
        "hashtags": ["#标签"],
        "account": "账号甲",
        "account_name": "账号甲",
        "follower_count": 11,
        "digg_count": 9,
        "collect_count": 8,
        "share_count": 7,
        "comment_count": 6,
        "duration_sec": 12.5,
        "publish_date": "2026-04-27",
        "content_type": "视频",
        "transcript": "口播自动转写",
        "transcript_status": "ok",
        "images": [],
        "image_count": 0,
        "cover": None,
        "frames": None,
        "play_count": 0,
        "video_file": None,
        "audio_file": None,
    }
    item.update(kwargs)
    return item


def base_row(**kwargs):
    row = {
        "rank": 1,
        "video_id": "100",
        "title": "人工标题",
        "title_short": "人工短标题",
        "cite_count": 3,
        "app_rate": 11.0,
        "original_desc": None,
        "hashtags": [],
        "account": "",
        "account_name": "暂未抓取到",
        "follower_count": "暂未获取",
        "digg_count": None,
        "collect_count": None,
        "share_count": None,
        "comment_count": None,
        "publish_date": "暂未抓取到",
        "content_type": None,
        "duration_sec": None,
        "transcript": None,
        "images": [],
        "image_count": None,
        "frame_count": None,
    }
    row.update(kwargs)
    return row


def filled_manual(**kwargs):
    row = base_row(
        original_desc="发布文案全文",
        post_desc="发布文案全文",
        hashtags=["#标签"],
        account="账号甲",
        account_name="账号甲",
        follower_count=11,
        digg_count=9,
        collect_count=8,
        share_count=7,
        comment_count=6,
        publish_date="2026-04-27",
        content_type="口播",
        duration_sec=12.5,
        transcript="口播自动转写",
        transcript_status="pending",
        images=["keep.jpg"],
        image_count=1,
        frame_count=1,
        post_title="平台发布标题",
        post_title_source="itemTitle",
    )
    row.update(kwargs)
    return row


class MergeFetchTests(unittest.TestCase):
    def test_fills_only_empty_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = base_row()
            pkg, fetch, original = write_case(
                tmp, [row], [base_item()], [status_row(1, "100", full=True)], trailing="\n"
            )
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = load_payload(pkg)
            got = rows_of(payload)[0]
            self.assertEqual(payload["STATS"], {"meta": {"keep": 1}, "app_rate": 11.0})
            self.assertEqual(got["original_desc"], "发布文案全文")
            self.assertEqual(got["post_desc"], "发布文案全文")
            self.assertEqual(got["hashtags"], ["#标签"])
            self.assertEqual(got["account"], "账号甲")
            self.assertEqual(got["account_name"], "账号甲")
            self.assertEqual(got["follower_count"], 11)
            self.assertEqual(got["digg_count"], 9)
            self.assertEqual(got["collect_count"], 8)
            self.assertEqual(got["share_count"], 7)
            self.assertEqual(got["comment_count"], 6)
            self.assertEqual(got["publish_date"], "2026-04-27")
            self.assertEqual(got["duration_sec"], 12.5)
            self.assertEqual(got["content_type"], "视频")
            self.assertEqual(got["transcript"], "口播自动转写")
            self.assertEqual(got["transcript_status"], "pending")
            self.assertEqual(got["post_title"], "平台发布标题")
            self.assertEqual(got["post_title_source"], "itemTitle")
            self.assertEqual(got["title"], "人工标题")
            self.assertEqual(got["title_short"], "人工短标题")
            self.assertEqual(got["cite_count"], 3)
            self.assertEqual(got["app_rate"], 11.0)
            self.assertNotIn("play_count", got)
            self.assertIn("需人工细分口播/混剪", result.stdout)
            text = (pkg / "gallery" / "data.json").read_bytes()
            self.assertTrue(text.endswith(b"\n"))
            self.assertFalse(text.endswith(b"\n\n"))
            self.assertIn('"app_rate": 11.0', text.decode("utf-8"))
            baks = list((pkg / "gallery").glob("data.json.bak-merge-*"))
            self.assertEqual(len(baks), 1)
            self.assertRegex(baks[0].name, r"^data\.json\.bak-merge-\d{14}$")
            self.assertEqual(baks[0].read_bytes(), original)
            self.assertFalse(list((pkg / "gallery").glob("*.tmp-merge")))
            _report, md = report_of(pkg)
            self.assertIn("模板不读 post_title / citation_title", md)
            alias = _report["original_desc_is_citation_title"]
            self.assertEqual(alias["title"], "original_desc 实为诊断包引用标题")
            self.assertEqual(alias["count"], 0)
            self.assertIn("## original_desc 实为诊断包引用标题", md)

    def test_does_not_overwrite_manual_values_including_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(
                digg_count=0,
                original_desc="人工文案",
                hashtags=["#保留"],
                publish_date="6月28日",
                eng_suspect_zero=False,
            )
            item = base_item(digg_count=9, original_desc="发布文案全文", hashtags=["#标签"], publish_date="2026-04-27")
            pkg, fetch, original = write_case(tmp, [row], [item], [status_row(1, "100", full=True)])
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["digg_count"], 0)
            self.assertEqual(got["original_desc"], "人工文案")
            self.assertEqual(got["hashtags"], ["#保留"])
            self.assertEqual(got["publish_date"], "6月28日")
            self.assertEqual(got["content_type"], "口播")
            self.assertEqual(got["title"], "人工标题")
            self.assertIn("冲突（未覆盖）", result.stdout)
            self.assertIn("人工 6月28日 / 脚本 2026-04-27", result.stdout)
            self.assertNotIn("人工 0 可疑", result.stdout)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)

    def test_marks_suspect_manual_zero_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(digg_count=0, eng_suspect_zero=True)
            item = base_item(digg_count=12)
            pkg, fetch, original = write_case(tmp, [row], [item], [status_row(1, "100", full=True)])
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["digg_count"], 0)
            self.assertIn("人工 0 可疑", result.stdout)
            self.assertIn("冲突（未覆盖）", result.stdout)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)

    def test_overwrite_reports_old_to_new_and_keeps_detailed_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(digg_count=3)
            item = base_item(digg_count=9)
            pkg, fetch, original = write_case(tmp, [row], [item], [status_row(1, "100", full=True)])
            result = run_merge(pkg, fetch, "--overwrite")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["digg_count"], 9)
            self.assertEqual(got["content_type"], "口播")
            self.assertEqual(got["title"], "人工标题")
            self.assertIn("3 → 9", result.stdout)
            report, md = report_of(pkg)
            self.assertTrue(any(row["field"] == "digg_count" and row["old"] == 3 and row["new"] == 9 for row in report["overwritten"]))
            self.assertIn("3 → 9", md)
            baks = list((pkg / "gallery").glob("data.json.bak-merge-*"))
            self.assertEqual(len(baks), 1)
            self.assertEqual(baks[0].read_bytes(), original)

    def test_missing_is_not_written_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="z1", digg_count=None),
                base_row(rank=2, video_id="z2", digg_count=None),
                base_row(rank=3, video_id="z3", digg_count=None),
                base_row(rank=4, video_id="z4", digg_count=0),
            ]
            items = [
                base_item(rank=1, video_id="z1", digg_count=None, title=None, original_desc=None, hashtags=[],
                          account=None, account_name=None, follower_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
                base_item(rank=2, video_id="z2", digg_count=0, title=None, original_desc=None, hashtags=[],
                          account=None, account_name=None, follower_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
                base_item(rank=3, video_id="z3", digg_count=0, title=None, original_desc=None, hashtags=[],
                          account=None, account_name=None, follower_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
                base_item(rank=4, video_id="z4", digg_count=0, title=None, original_desc=None, hashtags=[],
                          account=None, account_name=None, follower_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
            ]
            statuses = [
                status_row(1, "z1", digg_count="missing"),
                status_row(2, "z2", digg_count="missing"),
                status_row(3, "z3", digg_count={"status": "ok", "reason": "平台返回 0"}),
                status_row(4, "z4", digg_count={"status": "ok", "reason": "平台返回 0"}),
            ]
            pkg, fetch, _original = write_case(tmp, rows, items, statuses)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertIsNone(got["z1"]["digg_count"])
            self.assertIsNone(got["z2"]["digg_count"])
            self.assertEqual(got["z3"]["digg_count"], 0)
            self.assertIsInstance(got["z3"]["digg_count"], int)
            self.assertEqual(got["z4"]["digg_count"], 0)
            report, md = report_of(pkg)
            zeros = [row for row in report["zeros_written"] if row["field"] == "digg_count"]
            self.assertEqual([row["video_id"] for row in zeros], ["z3"])
            self.assertEqual(zeros[0]["field_status"], "ok")
            self.assertIn("平台返回 0", zeros[0]["reason"])
            self.assertIn("平台返回 0", md)

    def test_partial_writes_ok_fields_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = base_row(digg_count=None, collect_count=None)
            item = base_item(
                digg_count=5, collect_count=9, title=None, original_desc=None, hashtags=[],
                account=None, account_name=None, follower_count=None, share_count=None,
                comment_count=None, duration_sec=None, publish_date=None, content_type=None,
                transcript=None, transcript_status=None,
            )
            fields = status_row(1, "100", digg_count="ok", collect_count="missing")
            pkg, fetch, _original = write_case(tmp, [row], [item], [fields])
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["digg_count"], 5)
            self.assertIsNone(got["collect_count"])

    def test_blocked_and_missing_items_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="b1", digg_count=None),
                base_row(rank=2, video_id="b2", digg_count=None),
            ]
            items = [
                base_item(rank=1, video_id="b1", status="blocked", digg_count=10),
                base_item(rank=2, video_id="b2", status="missing", digg_count=10),
            ]
            statuses = [status_row(1, "b1", full=True), status_row(2, "b2", full=True)]
            media = {"media/01/01_1.jpg": b"img"}
            pkg, fetch, original = write_case(tmp, rows, items, statuses, media=media)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))
            self.assertIsNone(got[0]["digg_count"])
            self.assertIsNone(got[1]["digg_count"])
            self.assertIsNone(got[0]["original_desc"])
            self.assertEqual(got[0]["title"], "人工标题")
            self.assertNotIn("post_title", got[0])
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            self.assertFalse((pkg / "gallery" / "images" / "douyin_fetch" / "01" / "01_1.jpg").exists())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = base_row(publish_date=None, images=[])
            item = base_item(
                content_type="图文", publish_date="2026-04-27", images=["media/01/01_1.jpg"],
                image_count=1, transcript=None, transcript_status="skipped_tuwen", duration_sec=None,
                title=None, original_desc=None, hashtags=[], account=None, account_name=None,
                follower_count=None, digg_count=None, collect_count=None, share_count=None, comment_count=None,
            )
            fields = status_row(1, "100", publish_time="ok", images="ok", content_type="ok")
            pkg, fetch, original = write_case(
                tmp, [row], [item], [fields], media={"media/01/01_1.jpg": b"jpg-bytes"}
            )
            result = run_merge(pkg, fetch, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            self.assertEqual(list((pkg / "gallery").glob("data.json.bak-merge-*")), [])
            self.assertFalse((pkg / "work").exists())
            self.assertFalse((pkg / "gallery" / "images").exists())
            self.assertFalse((pkg / "shots").exists())
            self.assertIn("未写盘", result.stdout)
            self.assertIn("2026-04-27", result.stdout)

    def test_aligns_by_video_id_and_reports_rank_and_side_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="vid-match", publish_date=None),
                base_row(rank=2, video_id="vid-data-only", publish_date=None),
            ]
            items = [
                base_item(
                    rank=9, video_id="vid-match", publish_date="2026-05-01", title=None, original_desc=None,
                    hashtags=[], account=None, account_name=None, follower_count=None, digg_count=None,
                    collect_count=None, share_count=None, comment_count=None, duration_sec=None,
                    content_type=None, transcript=None, transcript_status=None,
                ),
                base_item(rank=4, video_id="vid-fetch-only", status="ok"),
            ]
            statuses = [
                status_row(9, "vid-match", publish_time="ok"),
                status_row(4, "vid-fetch-only", full=True),
            ]
            pkg, fetch, _original = write_case(tmp, rows, items, statuses)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["vid-match"]["publish_date"], "2026-05-01")
            self.assertEqual(got["vid-match"]["rank"], 1)
            self.assertIsNone(got["vid-data-only"]["publish_date"])
            self.assertIn("rank 不一致", result.stdout)
            self.assertIn("data rank 1 / fetch rank 9", result.stdout)
            self.assertIn("仅 data", result.stdout)
            self.assertIn("vid-data-only", result.stdout)
            self.assertIn("仅 fetch", result.stdout)
            self.assertIn("vid-fetch-only", result.stdout)
            report, _md = report_of(pkg)
            self.assertEqual(report["alignment"]["rank_mismatch"][0]["video_id"], "vid-match")
            self.assertEqual([row["video_id"] for row in report["alignment"]["only_data"]], ["vid-data-only"])
            self.assertEqual([row["video_id"] for row in report["alignment"]["only_fetch"]], ["vid-fetch-only"])

    def test_ranks_limit_which_rows_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="r1", publish_date=None),
                base_row(rank=2, video_id="r2", publish_date=None),
            ]
            items = [
                base_item(rank=1, video_id="r1", publish_date="2026-01-02", title=None, original_desc=None,
                          hashtags=[], account=None, account_name=None, follower_count=None, digg_count=None,
                          collect_count=None, share_count=None, comment_count=None, duration_sec=None,
                          content_type=None, transcript=None, transcript_status=None),
                base_item(rank=2, video_id="r2", publish_date="2026-03-04", title=None, original_desc=None,
                          hashtags=[], account=None, account_name=None, follower_count=None, digg_count=None,
                          collect_count=None, share_count=None, comment_count=None, duration_sec=None,
                          content_type=None, transcript=None, transcript_status=None),
            ]
            statuses = [status_row(1, "r1", publish_time="ok"), status_row(2, "r2", publish_time="ok")]
            pkg, fetch, _original = write_case(tmp, rows, items, statuses)
            result = run_merge(pkg, fetch, "--ranks", "1")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["r1"]["publish_date"], "2026-01-02")
            self.assertIsNone(got["r2"]["publish_date"])

    def test_transcript_fill_and_existing_transcript_get_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="t1", transcript=None, content_type="口播"),
                base_row(rank=2, video_id="t2", transcript="人工已有口播", content_type="口播"),
            ]
            items = [
                base_item(rank=1, video_id="t1", transcript="自动转写全文", transcript_status="ok",
                          title=None, original_desc=None, hashtags=[], account=None, account_name=None,
                          follower_count=None, digg_count=None, collect_count=None, share_count=None,
                          comment_count=None, duration_sec=None, publish_date=None, content_type="视频"),
                base_item(rank=2, video_id="t2", transcript="另一份转写", transcript_status="ok",
                          title=None, original_desc=None, hashtags=[], account=None, account_name=None,
                          follower_count=None, digg_count=None, collect_count=None, share_count=None,
                          comment_count=None, duration_sec=None, publish_date=None, content_type="视频"),
            ]
            statuses = [
                status_row(1, "t1", transcript="ok", content_type="ok"),
                status_row(2, "t2", transcript="ok", content_type="ok"),
            ]
            pkg, fetch, _original = write_case(tmp, rows, items, statuses)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["t1"]["transcript"], "自动转写全文")
            self.assertEqual(got["t1"]["transcript_status"], "pending")
            self.assertEqual(got["t2"]["transcript"], "人工已有口播")
            self.assertEqual(got["t2"]["transcript_status"], "pending")
            self.assertEqual(got["t2"]["content_type"], "口播")
            report, md = report_of(pkg)
            self.assertEqual(report["transcript_status_backfill"]["count"], 1)
            self.assertEqual(report["transcript_status_backfill"]["video_ids"], ["t2"])
            self.assertIn("未核对一律 pending", md)

    def test_post_title_and_citation_title_do_not_change_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = base_row(title="人工标题", title_short="人工短标题", video_id="100")
            item = base_item(title="平台发布标题", title_source="desc")
            top = {"videos": [{"video_id": 100, "title": "AI引用标题"}]}
            pkg, fetch, _original = write_case(
                tmp, [row], [item], [status_row(1, "100", full=True)], top=top
            )
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["title"], "人工标题")
            self.assertEqual(got["title_short"], "人工短标题")
            self.assertEqual(got["post_title"], "平台发布标题")
            self.assertEqual(got["post_title_source"], "desc")
            self.assertEqual(got["citation_title"], "AI引用标题")
            self.assertIn("模板不读 post_title / citation_title，页面不变", result.stdout)

    def test_copies_images_into_subdir_and_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(
                    rank=1, video_id="img", content_type="图文", images=[], image_count=None,
                    original_desc="发布文案全文", hashtags=["#标签"], account="账号甲", account_name="账号甲",
                    follower_count=11, digg_count=9, collect_count=8, share_count=7, comment_count=6,
                    publish_date="2026-04-27", transcript=None, duration_sec=None,
                    post_title="图文标题", post_title_source="itemTitle",
                ),
                filled_manual(
                    rank=2, video_id="vid", content_type="口播", images=[], frame_count=None,
                    post_title="平台发布标题",
                ),
            ]
            items = [
                base_item(
                    rank=1, video_id="img", content_type="图文", title="图文标题", title_source="itemTitle",
                    images=["media/01/01_1.jpg", "media/01/01_2.jpg"], image_count=2,
                    transcript=None, transcript_status="skipped_tuwen", duration_sec=None,
                ),
                base_item(
                    rank=2, video_id="vid", content_type="视频",
                    cover="media/02/02_cover.jpg",
                    frames=[{"file": "media/02/02_f1.jpg", "timestamp_sec": 0.5}],
                    video_file="media/02/02.mp4", audio_file="media/02/02.m4a", image_count=0,
                ),
            ]
            statuses = [
                status_row(1, "img", full=True, duration_sec="not_applicable", transcript="not_applicable",
                           frames="not_applicable", video_file="not_applicable"),
                status_row(2, "vid", full=True, images="not_applicable"),
            ]
            media = {
                "media/01/01_1.jpg": b"new-1",
                "media/01/01_2.jpg": b"new-2",
                "media/02/02_cover.jpg": b"cover",
                "media/02/02_f1.jpg": b"frame",
                "media/02/02.mp4": b"video",
                "media/02/02.m4a": b"audio",
            }
            pkg, fetch, _original = write_case(tmp, rows, items, statuses, media=media)
            existing = pkg / "gallery" / "images" / "douyin_fetch" / "01" / "01_2.jpg"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"old-2")
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["img"]["images"], ["douyin_fetch/01/01_1.jpg"])
            self.assertEqual(got["img"]["content_type"], "图文")
            images = pkg / "gallery" / "images"
            shots = pkg / "shots"
            self.assertEqual((images / "douyin_fetch/01/01_1.jpg").read_bytes(), b"new-1")
            self.assertEqual(existing.read_bytes(), b"old-2")
            self.assertEqual((shots / "douyin_fetch/01/01_1.jpg").read_bytes(), b"new-1")
            self.assertEqual(got["vid"]["images"], ["douyin_fetch/02/02_cover.jpg", "douyin_fetch/02/02_f1.jpg"])
            self.assertEqual(got["vid"]["frame_count"], 1)
            self.assertFalse((images / "douyin_fetch/02/02.mp4").exists())
            self.assertFalse((images / "douyin_fetch/02/02.m4a").exists())
            self.assertFalse((shots / "douyin_fetch/02/02.mp4").exists())
            self.assertFalse((shots / "douyin_fetch/02/02.m4a").exists())
            self.assertEqual((shots / "douyin_fetch/02/02_cover.jpg").read_bytes(), b"cover")
            self.assertEqual((shots / "douyin_fetch/02/02_f1.jpg").read_bytes(), b"frame")
            self.assertEqual((images / "douyin_fetch/02/02_cover.jpg").read_bytes(), b"cover")
            self.assertIn("同名文件内容不同，未覆盖", result.stdout)
            self.assertIn("视频未复制", result.stdout)
            self.assertIn("仍在 fetch 输出目录", result.stdout)
            report, _md = report_of(pkg)
            skipped = report["videos_not_copied"]
            self.assertEqual(
                [(row["src"], row["exists"]) for row in skipped],
                [("media/02/02.mp4", True), ("media/02/02.m4a", True)],
            )
            self.assertFalse(any(op["src"].endswith((".mp4", ".m4a")) for op in report["file_ops"]))

    def test_empty_script_hashtags_do_not_fill_or_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="h1", hashtags=["#保留"]),
                base_row(rank=2, video_id="h2", hashtags=[]),
            ]
            items = [
                base_item(rank=1, video_id="h1", hashtags=[], title=None, original_desc=None, account=None,
                          account_name=None, follower_count=None, digg_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
                base_item(rank=2, video_id="h2", hashtags=["#新"], title=None, original_desc=None, account=None,
                          account_name=None, follower_count=None, digg_count=None, collect_count=None,
                          share_count=None, comment_count=None, duration_sec=None, publish_date=None,
                          content_type=None, transcript=None, transcript_status=None),
            ]
            statuses = [
                status_row(1, "h1", hashtags={"status": "ok", "reason": "无标签"}),
                status_row(2, "h2", hashtags="ok"),
            ]
            pkg, fetch, _original = write_case(tmp, rows, items, statuses)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["h1"]["hashtags"], ["#保留"])
            self.assertEqual(got["h2"]["hashtags"], ["#新"])

    def test_preserves_list_payload_and_newline_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = base_row(publish_date=None)
            item = base_item(
                publish_date="2026-08-08", title=None, original_desc=None, hashtags=[], account=None,
                account_name=None, follower_count=None, digg_count=None, collect_count=None,
                share_count=None, comment_count=None, duration_sec=None, content_type=None,
                transcript=None, transcript_status=None,
            )
            pkg, fetch, _original = write_case(
                tmp, [row], [item], [status_row(1, "100", publish_time="ok")], trailing="", kind="list"
            )
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            raw = (pkg / "gallery" / "data.json").read_bytes()
            self.assertFalse(raw.endswith(b"\n"))
            payload = json.loads(raw.decode("utf-8"))
            self.assertIsInstance(payload, list)
            self.assertEqual(payload[0]["publish_date"], "2026-08-08")
            self.assertEqual(payload[0]["title"], "人工标题")

    def test_whitespace_only_difference_is_not_a_conflict(self):
        manual = "第一行  第二行\n第三行"
        script = " 第一行 第二行 第三行 "
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(original_desc=manual, post_desc=script)
            pkg, fetch, original = write_case(
                tmp, [row], [base_item(original_desc=script)], [status_row(1, "100", full=True)]
            )
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["original_desc"], manual)
            self.assertIn("\n", got["original_desc"])
            self.assertIn("只差空白", result.stdout)
            report, md = report_of(pkg)
            self.assertFalse(any(item["field"] == "original_desc" for item in report["conflicts"]))
            self.assertFalse(any(item["field"] == "original_desc" for item in report["overwritten"]))
            self.assertIn("## 冲突（未覆盖）\n\n无", md)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(original_desc=manual, post_desc=script)
            pkg, fetch, original = write_case(
                tmp, [row], [base_item(original_desc=script)], [status_row(1, "100", full=True)]
            )
            result = run_merge(pkg, fetch, "--overwrite")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["original_desc"], manual)
            report, md = report_of(pkg)
            self.assertFalse(any(item["field"] == "original_desc" for item in report["overwritten"]))
            self.assertIn("## 覆盖（旧值 → 新值）\n\n无", md)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)

    def test_post_desc_filled_and_citation_title_alias_reported(self):
        citation = "十大净水器品牌排名与选购关键参数解析（诊断包引用标题，不是作者写在作品下的发布文案）"
        post = "家人们这台净水器我用了三个月，通量、换芯和安装费分开说，别只看标题里的排名和广告词。"
        manual2 = "这是作者自己写的发布文案，和诊断包标题不是同一句。"
        self.assertGreater(len(citation), 40)
        self.assertGreater(len(post), 40)
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                base_row(rank=1, video_id="100", original_desc=citation),
                base_row(rank=2, video_id="200", original_desc=manual2),
                base_row(rank=3, video_id="300", original_desc=None),
            ]
            items = [
                base_item(rank=1, video_id="100", original_desc=post),
                base_item(rank=2, video_id="200", original_desc=post),
                base_item(rank=3, video_id="300", original_desc="不应写入"),
            ]
            statuses = [
                status_row(1, "100", full=True),
                status_row(2, "200", full=True),
                status_row(3, "300", desc="missing"),
            ]
            top = {"videos": [
                {"video_id": "100", "title": citation},
                {"video_id": "200", "title": citation},
            ]}
            pkg, fetch, _original = write_case(tmp, rows, items, statuses, top=top)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = {row["video_id"]: row for row in rows_of(load_payload(pkg))}
            self.assertEqual(got["100"]["original_desc"], citation)
            self.assertEqual(got["100"]["post_desc"], post)
            self.assertEqual(got["100"]["citation_title"], citation)
            self.assertEqual(got["100"]["title"], "人工标题")
            self.assertEqual(got["200"]["original_desc"], manual2)
            self.assertEqual(got["200"]["post_desc"], post)
            self.assertIsNone(got["300"]["original_desc"])
            self.assertNotIn("post_desc", got["300"])
            report, md = report_of(pkg)
            alias = report["original_desc_is_citation_title"]
            self.assertEqual(alias["title"], "original_desc 实为诊断包引用标题")
            self.assertIn("--overwrite-fields original_desc", alias["note"])
            self.assertEqual(alias["count"], 1)
            self.assertEqual(alias["entries"][0]["rank"], 1)
            self.assertEqual(alias["entries"][0]["video_id"], "100")
            self.assertEqual(alias["entries"][0]["original_desc"], citation[:40])
            self.assertEqual(alias["entries"][0]["post_desc"], post[:40])
            self.assertIn("## original_desc 实为诊断包引用标题", md)
            self.assertIn(citation[:40], md)
            self.assertIn(post[:40], md)
            self.assertIn("rank 1 video_id 100：original_desc「", md)
            self.assertNotIn("rank 2 video_id 200：original_desc「", md)

    def test_overwrite_fields_only_updates_listed_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(
                original_desc="人工文案",
                post_desc="已有发布文案",
                digg_count=3,
                collect_count=2,
            )
            item = base_item(original_desc="发布文案全文", digg_count=9, collect_count=8)
            pkg, fetch, _original = write_case(tmp, [row], [item], [status_row(1, "100", full=True)])
            result = run_merge(pkg, fetch, "--overwrite-fields", "original_desc,digg_count")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["original_desc"], "发布文案全文")
            self.assertEqual(got["post_desc"], "已有发布文案")
            self.assertEqual(got["digg_count"], 9)
            self.assertEqual(got["collect_count"], 2)
            self.assertEqual(got["content_type"], "口播")
            report, md = report_of(pkg)
            self.assertEqual([item["field"] for item in report["overwritten"]], ["original_desc", "digg_count"])
            self.assertEqual(
                {item["field"] for item in report["conflicts"]},
                {"collect_count", "post_desc"},
            )
            self.assertIn("人工文案", md)
            self.assertIn("只覆盖 original_desc、digg_count", md)

    def test_overwrite_flag_overrides_overwrite_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(original_desc="人工文案", digg_count=3, post_desc="已有发布文案")
            item = base_item(original_desc="发布文案全文", digg_count=9)
            pkg, fetch, _original = write_case(tmp, [row], [item], [status_row(1, "100", full=True)])
            result = run_merge(pkg, fetch, "--overwrite", "--overwrite-fields", "original_desc")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["original_desc"], "发布文案全文")
            self.assertEqual(got["post_desc"], "发布文案全文")
            self.assertEqual(got["digg_count"], 9)
            self.assertEqual(got["content_type"], "口播")
            report, md = report_of(pkg)
            self.assertTrue(report["params"]["overwrite"])
            self.assertEqual(report["params"]["overwrite_fields"], ["original_desc"])
            self.assertEqual(report["mode"], "overwrite")
            self.assertTrue(any("以 --overwrite（全部字段）为准" in note for note in report["notes"]))
            self.assertIn("以 --overwrite（全部字段）为准", md)
            overwritten = {item["field"] for item in report["overwritten"]}
            self.assertIn("digg_count", overwritten)
            self.assertIn("original_desc", overwritten)
            self.assertIn("post_desc", overwritten)
            self.assertNotIn("content_type", overwritten)

    def test_unknown_overwrite_field_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, original = write_case(
                tmp, [base_row()], [base_item()], [status_row(1, "100", full=True)]
            )
            bad = run_merge(pkg, fetch, "--overwrite-fields", "original_desc,no_such_field")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("未知字段", bad.stderr)
            self.assertIn("no_such_field", bad.stderr)
            self.assertIn("可用字段：", bad.stderr)
            self.assertNotIn("content_type", bad.stderr.split("可用字段：", 1)[1])
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            self.assertFalse((pkg / "work").exists())
            empty = run_merge(pkg, fetch, "--overwrite-fields", " , ")
            self.assertNotEqual(empty.returncode, 0)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)

    def test_cover_supplement_copies_shots_not_images(self):
        media = {
            "media/01/01_cover.jpg": b"cover",
            "media/01/01_f1.jpg": b"frame1",
            "media/01/01_f2.jpg": b"frame2",
            "media/01/01.mp4": b"video",
            "media/01/01.m4a": b"audio",
        }
        item = base_item(
            content_type="视频",
            cover="media/01/01_cover.jpg",
            frames=[
                {"file": "media/01/01_f1.jpg", "timestamp_sec": 0.5},
                {"file": "media/01/01_f2.jpg", "timestamp_sec": 1.5},
            ],
            video_file="media/01/01.mp4",
            audio_file="media/01/01.m4a",
        )
        row = filled_manual(
            content_type="口播",
            images=["01_cover.jpg"],
            capture_status="cover_only",
            frame_count=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, original = write_case(
                tmp, [row], [item], [status_row(1, "100", full=True)], media=media
            )
            dry = run_merge(pkg, fetch, "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr + dry.stdout)
            self.assertIn("可补图（未改）", dry.stdout)
            self.assertFalse((pkg / "gallery" / "images" / "douyin_fetch").exists())
            self.assertFalse((pkg / "shots").exists())
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["images"], ["01_cover.jpg"])
            self.assertFalse((pkg / "gallery" / "images" / "douyin_fetch").exists())
            shot = pkg / "shots" / "douyin_fetch" / "01"
            self.assertEqual((shot / "01_cover.jpg").read_bytes(), b"cover")
            self.assertEqual((shot / "01_f1.jpg").read_bytes(), b"frame1")
            self.assertEqual((shot / "01_f2.jpg").read_bytes(), b"frame2")
            self.assertFalse((shot / "01.mp4").exists())
            self.assertFalse((shot / "01.m4a").exists())
            self.assertIn("人工 1 张 / 脚本 3 张，可补图（未改）", result.stdout)
            self.assertIn("视频未复制", result.stdout)
            self.assertIn("仍在 fetch 输出目录", result.stdout)
            report, _md = report_of(pkg)
            self.assertTrue(report["file_ops"])
            self.assertFalse(any(op["where"] == "images" for op in report["file_ops"]))
            self.assertTrue(any(op["where"] == "shots" and op["action"] == "copied" for op in report["file_ops"]))
        with tempfile.TemporaryDirectory() as tmp:
            row = filled_manual(
                content_type="口播",
                images=["01_cover.jpg"],
                capture_status="cover_only",
                frame_count=1,
                digg_count=3,
            )
            pkg, fetch, _original = write_case(
                tmp, [row], [item], [status_row(1, "100", full=True)], media=media
            )
            result = run_merge(pkg, fetch, "--overwrite-fields", "images")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            got = rows_of(load_payload(pkg))[0]
            self.assertEqual(got["images"], [
                "douyin_fetch/01/01_cover.jpg",
                "douyin_fetch/01/01_f1.jpg",
                "douyin_fetch/01/01_f2.jpg",
            ])
            self.assertEqual(got["digg_count"], 3)
            image = pkg / "gallery" / "images" / "douyin_fetch" / "01"
            shot = pkg / "shots" / "douyin_fetch" / "01"
            self.assertEqual((image / "01_f1.jpg").read_bytes(), b"frame1")
            self.assertEqual((shot / "01_f1.jpg").read_bytes(), b"frame1")
            self.assertFalse((shot / "01.mp4").exists())
            self.assertFalse((shot / "01.m4a").exists())
            self.assertFalse((image / "01.mp4").exists())
            self.assertFalse((image / "01.m4a").exists())
            self.assertIn("## 可补图（未改）\n\n无", result.stdout)

    def test_default_skips_mp4_m4a_until_shots_video(self):
        media = {
            "media/01/01_cover.jpg": b"cover",
            "media/01/01_f1.jpg": b"frame",
            "media/01/01.mp4": b"video",
            "media/01/01.m4a": b"audio",
        }
        item = base_item(
            content_type="视频",
            cover="media/01/01_cover.jpg",
            frames=[{"file": "media/01/01_f1.jpg", "timestamp_sec": 0.5}],
            video_file="media/01/01.mp4",
            audio_file="media/01/01.m4a",
            image_count=0,
        )
        row = base_row(images=[], content_type=None)
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, original = write_case(
                tmp, [row], [item], [status_row(1, "100", full=True)], media=media
            )
            dry = run_merge(pkg, fetch, "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr + dry.stdout)
            self.assertIn("视频未复制", dry.stdout)
            self.assertIn("仍在 fetch 输出目录", dry.stdout)
            self.assertIn("--shots-video", dry.stdout)
            self.assertIn("shots-video：否", dry.stdout)
            self.assertFalse((pkg / "shots").exists())
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            result = run_merge(pkg, fetch)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            shot = pkg / "shots" / "douyin_fetch" / "01"
            images = pkg / "gallery" / "images" / "douyin_fetch" / "01"
            self.assertEqual((shot / "01_cover.jpg").read_bytes(), b"cover")
            self.assertEqual((shot / "01_f1.jpg").read_bytes(), b"frame")
            self.assertEqual((images / "01_cover.jpg").read_bytes(), b"cover")
            self.assertFalse((shot / "01.mp4").exists())
            self.assertFalse((shot / "01.m4a").exists())
            self.assertFalse((images / "01.mp4").exists())
            self.assertFalse((images / "01.m4a").exists())
            report, md = report_of(pkg)
            self.assertFalse(report["params"]["shots_video"])
            self.assertEqual([row["src"] for row in report["videos_not_copied"]], ["media/01/01.mp4", "media/01/01.m4a"])
            self.assertIn("视频未复制 2 个：mp4 / m4a 默认不复制进 shots，仍在 fetch 输出目录。需要时加 --shots-video。", md)
            self.assertIn("- rank 1 video_id 100：media/01/01.mp4", md)
            self.assertIn("- rank 1 video_id 100：media/01/01.m4a", md)
            self.assertFalse(any(op["src"].endswith((".mp4", ".m4a")) for op in report["file_ops"]))
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, _original = write_case(
                tmp, [row], [item], [status_row(1, "100", full=True)], media=media
            )
            result = run_merge(pkg, fetch, "--shots-video")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            shot = pkg / "shots" / "douyin_fetch" / "01"
            images = pkg / "gallery" / "images" / "douyin_fetch" / "01"
            self.assertEqual((shot / "01.mp4").read_bytes(), b"video")
            self.assertEqual((shot / "01.m4a").read_bytes(), b"audio")
            self.assertEqual((shot / "01_f1.jpg").read_bytes(), b"frame")
            self.assertFalse((images / "01.mp4").exists())
            self.assertFalse((images / "01.m4a").exists())
            report, md = report_of(pkg)
            self.assertTrue(report["params"]["shots_video"])
            self.assertEqual(report["videos_not_copied"], [])
            self.assertNotIn("视频未复制", md)
            self.assertIn("shots-video：是", md)
            copied = {op["src"] for op in report["file_ops"] if op["action"] == "copied" and op["where"] == "shots"}
            self.assertIn("media/01/01.mp4", copied)
            self.assertIn("media/01/01.m4a", copied)

    def test_overwrite_fields_content_type_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, original = write_case(
                tmp, [filled_manual(content_type="口播")], [base_item()], [status_row(1, "100", full=True)]
            )
            alone = run_merge(pkg, fetch, "--overwrite-fields", "content_type")
            self.assertNotEqual(alone.returncode, 0)
            self.assertIn("content_type 不支持覆盖，只在人工为空时填", alone.stderr)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            self.assertFalse((pkg / "work").exists())
            mixed = run_merge(pkg, fetch, "--overwrite-fields", "original_desc,content_type")
            self.assertNotEqual(mixed.returncode, 0)
            self.assertIn("content_type 不支持覆盖，只在人工为空时填", mixed.stderr)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)
            self.assertFalse((pkg / "shots").exists())
            with_all = run_merge(pkg, fetch, "--overwrite", "--overwrite-fields", "content_type")
            self.assertNotEqual(with_all.returncode, 0)
            self.assertIn("content_type 不支持覆盖，只在人工为空时填", with_all.stderr)
            self.assertEqual((pkg / "gallery" / "data.json").read_bytes(), original)

    def test_bad_args_exit_nonzero(self):
        result = run_merge("/no/such/package", "/no/such/fetch")
        self.assertNotEqual(result.returncode, 0)
        with tempfile.TemporaryDirectory() as tmp:
            pkg, fetch, _original = write_case(
                tmp, [base_row()], [base_item()], [status_row(1, "100", full=True)]
            )
            bad = run_merge(pkg, fetch, "--ranks", "a")
            self.assertNotEqual(bad.returncode, 0)
            missing = run_merge(pkg, fetch, "--data", "missing.json")
            self.assertNotEqual(missing.returncode, 0)


if __name__ == "__main__":
    unittest.main()
