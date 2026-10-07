"""Evidence preservation and packaging regression tests; no network or client data."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from fetch_video_scripts import write_template
from normalize_hashtags import _patch_obj


class EvidenceSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pkg = Path(self.tmp.name)
        (self.pkg / '_机器可读').mkdir()
        (self.pkg / '文案').mkdir()
        self.top = self.pkg / '_机器可读/top.json'

    def save(self, videos):
        self.top.write_text(json.dumps({'videos': videos}), encoding='utf8')

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / name), '--package', str(self.pkg), *args], capture_output=True, text=True)

    def test_verify_preserves_short_body_metadata_and_missing_record(self):
        path = self.pkg / '文案/1.md'
        content = '# 视频\n> 来源：https://example.org/1\n> 账号：\n> 文案类型：发布文案\n> 拉取状态：已拉取\n\n---\n\n短但真实的描述。\n'
        path.write_text(content)
        self.save([{'rank': 1, 'url': 'https://example.org/1', 'title': '视频', 'script_path': '文案/1.md', 'account': '已有账号'},
                   {'rank': 2, 'title': '缺文件', 'script_path': '文案/2.md', 'fetch_status': 'ok'}])
        result = self.run_script('fetch_video_scripts.py', '--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        first, missing = json.loads(self.top.read_text())['videos']
        self.assertEqual(path.read_text(), content)
        self.assertEqual(first['account'], '已有账号')
        self.assertEqual(first['fetch_status'], 'ok')
        self.assertTrue(first['eligibility']['caption'])
        self.assertFalse(first['eligibility']['transcript'])
        self.assertEqual(missing['fetch_status'], 'fail')
        self.assertEqual(missing['fail_reason'], '缺文件')
        self.assertFalse((self.pkg / '文案/2.md').exists())

    def test_init_never_overwrites_small_existing_file(self):
        p = self.pkg / '文案/existing.md'
        p.write_text('已有')
        self.assertFalse(write_template(str(p), {}))
        self.assertEqual(p.read_text(), '已有')

    def test_unknown_body_is_not_transcript_and_pending_is_retained(self):
        p = self.pkg / '文案/1.md'
        p.write_text('> 来源：https://example.org\n> 拉取状态：已拉取\n\n---\n' + '未知正文' * 60)
        self.save([{'rank': 1, 'script_path': '文案/1.md'}, {'rank': 2, 'script_path': '文案/2.md'}])
        write_template(str(self.pkg / '文案/2.md'), {})
        result = self.run_script('fetch_video_scripts.py', '--verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        first, second = json.loads(self.top.read_text())['videos']
        self.assertFalse(first['eligibility']['transcript'])
        self.assertEqual(second['fetch_status'], 'pending')

    def test_normalization_preserves_source_and_all_analytical_tags(self):
        source = ['＃ＡＩ', '#ai', '#一', '#二', '#三', '#四', '#五', '#六']
        obj = {'hashtags': source[:]}
        _patch_obj(obj)
        self.assertEqual(obj['hashtags_raw'], source)
        self.assertEqual(len(obj['hashtags']), 7)
        self.assertNotIn('hashtags_display', obj)
        _patch_obj(obj, 2)
        self.assertEqual(len(obj['hashtags']), 7)
        self.assertEqual(len(obj['hashtags_display']), 2)
        self.assertEqual(obj['hashtags_raw'], source)

    def test_finalize_retains_process_and_accepts_short_verified_body(self):
        for name in ('README.md', '视频索引.md'):
            (self.pkg / name).write_text('真实检查夹文件。' * 10)
        (self.pkg / 'gallery/images').mkdir(parents=True)
        (self.pkg / 'gallery/index.html').write_text('<html>' + '有效页面占位测试' * 50 + '</html>')
        (self.pkg / '_过程').mkdir()
        evidence = self.pkg / '_过程/evidence.txt'
        evidence.write_text('不可删除的证据')
        (self.pkg / '文案/1.md').write_text('> 拉取状态：已拉取\n\n---\n短文案。')
        self.save([{'script_path': '文案/1.md', 'fetch_status': 'ok'}])
        result = self.run_script('finalize_package.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(evidence.exists())
        self.assertNotIn('交付完成', result.stdout)
        self.save([{'script_path': '文案/1.md', 'fetch_status': 'pending'}])
        result = self.run_script('finalize_package.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(evidence.exists())


if __name__ == '__main__':
    unittest.main()
