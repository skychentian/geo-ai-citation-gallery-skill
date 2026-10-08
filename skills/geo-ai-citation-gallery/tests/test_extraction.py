import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('extract_top_videos')


def row(url='https://www.douyin.com/video/123', question='怎么选', platform='A', answer_id='1'):
    return dict(url=url, question=question, platform_name=platform, answer_id=answer_id,
                title='样本', site='抖音', stage='exploration')


class ExtractionTests(unittest.TestCase):
    def test_video_identity(self):
        links = ['https://www.douyin.com/video/123',
                 'https://www.iesdouyin.com/share/video/123',
                 'https://www.douyin.com/note/123',
                 'https://www.douyin.com/?modal_id=123']
        self.assertEqual(len({m.normalize_url(x) for x in links}), 1)
        self.assertNotEqual(m.normalize_url(links[-1]), m.normalize_url('https://www.douyin.com/?modal_id=456'))
        self.assertNotEqual(m.normalize_url('https://other.test/?modal_id=123'),
                            m.normalize_url('https://other.test/?modal_id=456'))

    def test_answer_question_and_raw_rows_are_distinct(self):
        item = m.aggregate([row(), row(), row(platform='B'), row(answer_id='2')])[0]
        self.assertEqual(item['citation_count'], 3)
        self.assertEqual(item['question_count'], 1)
        self.assertEqual(item['total_pickups'], 4)
        self.assertEqual(item['ranking_metric'], 'citation_count')

    def test_missing_answer_id_uses_one_explicit_ranking_metric(self):
        same = row(url='https://www.douyin.com/video/456', answer_id='')
        same.update(round=1, response_index=1)
        duplicate = dict(same)
        shifted = dict(same, response_index=2)
        items = m.aggregate([row(), same, duplicate, shifted])
        self.assertTrue(all(x['ranking_metric'] == 'citation_count' for x in items))
        missing = next(x for x in items if x['video_id'] == '456')
        self.assertEqual(missing['citation_count_status'], 'link_occurrence')
        self.assertEqual(missing['citation_count'], 2)
        self.assertEqual(m.aggregate([same, duplicate])[0]['citation_count'], 1)

    def test_question_platform_mapping_does_not_leak_other_platforms(self):
        item = m.aggregate([row(), row(question='多少钱', platform='B')])[0]
        self.assertEqual(item['question_platforms'], {'怎么选': ['A'], '多少钱': ['B']})

    def test_cutoff_ties_use_selected_metric(self):
        items = m.aggregate([row(answer_id=''), row(url='https://www.douyin.com/video/456', answer_id='')])
        top, tied = m._split_ties(items, 1)
        self.assertEqual(len(top), 1)
        self.assertEqual(len(tied), 2)

    def test_cli_fallback_and_existing_results_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, out = Path(tmp) / 'source.csv', Path(tmp) / 'package'
            records = [row(answer_id=''), row(platform='B', answer_id='')]
            with csv_path.open('w') as f:
                writer = csv.DictWriter(f, fieldnames=records[0].keys())
                writer.writeheader(); writer.writerows(records)
            cmd = [sys.executable, '-B', str(SCRIPTS / 'extract_top_videos.py'), '--csv', str(csv_path),
                   '--brand', '测试品牌', '--package-date', '20260923', '--out', str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = out / '_机器可读/top.json'
            before = path.read_bytes()
            doc = json.loads(before)
            self.assertEqual(doc['meta']['schema_version'], 2)
            self.assertIsNone(doc['meta']['total_answers'])
            self.assertEqual(doc['videos'][0]['citation_count'], 2)
            self.assertEqual(doc['videos'][0]['citation_count_status'], 'link_occurrence')
            self.assertIn('链接出现口径', (out / '视频索引.md').read_text())
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(before, path.read_bytes())

    def test_bare_icons_do_not_invent_zero(self):
        engagement = load('fetch_engagement')

        class Page:
            url = 'https://www.douyin.com/video/123'
            def goto(self, *args, **kwargs): pass
            def wait_for_timeout(self, *args): pass
            def evaluate(self, *args):
                return dict(zeroDisplay=True, login=False, digg=None, collect=None)

        result = engagement.fetch_one(Page(), {'rank': 1, 'video_id': '123', 'url': Page.url}, wait_ms=0)
        self.assertEqual(result['status'], 'missing')
        for field in ('digg_count', 'collect_count', 'share_count', 'comment_count'):
            self.assertIsNone(result[field])


if __name__ == '__main__':
    unittest.main()
