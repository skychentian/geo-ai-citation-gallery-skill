import base64,hashlib,importlib.util,json,re,tempfile,unittest
from html.parser import HTMLParser
from pathlib import Path
spec=importlib.util.spec_from_file_location('build',Path(__file__).resolve().parents[1]/'scripts/build_report.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ContractTests(unittest.TestCase):
 def setUp(self):
  self.r={1:{'title':'测试','cite_count':2,'original_desc':'甲。乙。','transcript':'甲。乙。'}}
  self.c={'rank':1,'heading':'写法','source_field':'original_desc','paragraphs':[{'text':'甲。乙。','point':'要点','note':'解释'}]}
 def test_complete_source(self):
  self.assertIn('甲。乙。',m.render_case(self.c,self.r,Path('/tmp'),False))
 def test_missing_cite_count_label(self):
  self.r[1]['cite_count']=None
  rendered=m.render_case(self.c,self.r,Path('/tmp'),False)
  self.assertIn('暂未获取',rendered)
  self.assertNotIn('None 次',rendered)
 def test_reject_excerpt(self):
  self.c['paragraphs'][0]['text']='甲。'
  with self.assertRaises(AssertionError):m.render_case(self.c,self.r,Path('/tmp'),False)
 def test_reject_unverified_transcript(self):
  self.c['source_field']='transcript'
  with self.assertRaises(AssertionError):m.render_case(self.c,self.r,Path('/tmp'),False)
 def test_pending_transcript_shows_review_notice(self):
  self.c['source_field']='transcript'
  self.r[1]['transcript_status']='pending'
  rendered=m.render_case(self.c,self.r,Path('/tmp'),False)
  self.assertIn('id="video-copy-1-review"',rendered)
  self.assertIn('自动转写，待核对',rendered)
  self.r[1]['transcript_status']='draft'
  with self.assertRaises(AssertionError):m.render_case(self.c,self.r,Path('/tmp'),False)
  del self.r[1]['transcript_status']
  with self.assertRaises(AssertionError):m.render_case(self.c,self.r,Path('/tmp'),False)
 def test_reject_missing_frames(self):
  with self.assertRaises(AssertionError):m.render_case(self.c,self.r,Path('/tmp'),True)
 def test_stable_case_copy_and_frame_ids(self):
  with tempfile.TemporaryDirectory() as folder:
   media=Path(folder)
   media.joinpath('1.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGPkMTrBwMDAxAAGAAu2AQrbn93yAAAAAElFTkSuQmCC'))
   self.c['frames']=[{'file':'1.png','label':'首图','source_ref':'capture-ledger.json:1/frames/0'}]
   detail=m.render_case(self.c,self.r,media,True)
   copy=m.render_case(self.c,self.r,media,False)
   for ident in ('video-case-1','video-case-1-text','video-case-1-frame-1'):
    self.assertIn('id="'+ident+'"',detail)
   for ident in ('video-copy-1','video-copy-1-text'):
    self.assertIn('id="'+ident+'"',copy)
   ids=re.findall(r'id="([^"]+)"',detail+copy)
   self.assertEqual(len(ids),len(set(ids)))
 def test_build_complete_fixture_preserves_approved_style(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);media=root/'frames';media.mkdir()
   media.joinpath('1.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGPkMTrBwMDAxAAGAAu2AQrbn93yAAAAAElFTkSuQmCC'))
   row={'rank':1,'video_id':'123','url':'https://douyin.com/note/123','title':'合成测试','cite_count':1,
        'content_type':'图文','images':['1.png'],'original_desc':'甲。乙。','image_text':'甲。乙。'}
   case=dict(self.c,source_field='image_text',frames=[{'file':'1.png','label':'首图','source_ref':'capture-ledger.json:123/frames/0'}])
   report={'client':'合成测试','images_dir':'frames','stats':{'meta':{'sample_n':1,'cite_sum':1,'sector':'合成测试',
           'monitor_date':'2026-09-24','platform':'合成测试'}},'data':[row],'findings':['合成测试']*5,
           'duration_reading':'合成测试','cases':[case],'copy_examples':[self.c]}
   source=root/'report.json';source.write_text(json.dumps(report))
   m.build(source,root/'output')
   rendered=(root/'output/index.html').read_text()
   self.assertIn('id="video-case-1-frame-1"',rendered)
   self.assertIn('video-copy-1-text',rendered)
   self.assertIn('id="sample-${r.rank}-frame-${j+1}"',rendered)
   original=(m.ROOT/'assets/template.html').read_text()
   styles=lambda value:re.findall(r'<style[^>]*>(.*?)</style>',value,re.S)
   self.assertEqual(styles(rendered),styles(original))
   self.assertEqual(hashlib.sha256(styles(rendered)[0].encode()).hexdigest(),'f3bc4ad1b6a53abfa640d0754c193de4f2d8d9f9f9128de10d7103fc1d0636f0')
   self.assertIn('transcript-open',rendered)
   self.assertIn('data-excl=',rendered)
   self.assertNotIn('{{CASES_HTML}}',rendered)
   report['client']='第二个合成客户';report['stats']['meta']['sector']='另一行业'
   source.write_text(json.dumps(report));m.build(source,root/'second-output')
   second=(root/'second-output/index.html').read_text()
   self.assertEqual(styles(second),styles(rendered))
   self.assertIn('data-print-label="另一行业 Top1"',second)
   self.assertIn('第二个合成客户',second)
   report['cases']=[case,case];source.write_text(json.dumps(report))
   with self.assertRaisesRegex(AssertionError,'Duplicate case ranks'):
    m.build(source,root/'duplicate-output')
 def test_script_escape(self):
  self.assertNotIn('</script>',m.js({'text':'</script><script>alert(1)</script>'}))
 def test_chart_fallback_uses_question_count_or_cite(self):
  stats={'meta':{}}
  data=[
   {'rank':1,'title':'甲','cite_count':None,'q_count':3,'digg_count':1500},
   {'rank':2,'title':'乙','cite_count':None,'q_count':5,'digg_count':500},
  ]
  self.assertEqual(m.chart_fallback(stats, data), 'q')
  self.assertEqual(stats['meta']['chart_y_metric'], 'question_count')
  self.assertEqual(stats['scatter'], [
   {'digg':1500,'cite':3,'rank':1,'title':'甲'},
   {'digg':500,'cite':5,'rank':2,'title':'乙'},
  ])
  self.assertEqual(stats['digg_vs_cite'], [
   {'bucket':'<1千','n':1,'avg_cite':5},
   {'bucket':'1千-1万','n':1,'avg_cite':3},
  ])
  cited={'meta':{}}
  self.assertEqual(m.chart_fallback(cited, [{'rank':1,'title':'甲','cite_count':4,'q_count':9,'digg_count':2000}]), 'cite')
  self.assertEqual(cited['scatter'], [{'digg':2000,'cite':4,'rank':1,'title':'甲'}])
  self.assertEqual(cited['digg_vs_cite'], [{'bucket':'1千-1万','n':1,'avg_cite':4}])
  self.assertEqual(cited['meta']['chart_y_metric'], 'citation_count')
  kept={'meta':{},'scatter':[{'digg':9,'cite':8,'rank':1,'title':'已有'}],'digg_vs_cite':[{'bucket':'<1千','n':1,'avg_cite':8}]}
  self.assertEqual(m.chart_fallback(kept, [{'rank':1,'title':'甲','cite_count':4,'q_count':9,'digg_count':2000}]), 'cite')
  self.assertEqual(kept['scatter'][0]['cite'], 8)
  self.assertEqual(kept['digg_vs_cite'][0]['avg_cite'], 8)
  labeled=m._relabel_chart_axes((m.ROOT/'assets/template.html').read_text())
  self.assertIn("text:'覆盖问题数（缺引用次数时替代）'", labeled)
  self.assertIn('纵轴覆盖问题数（缺引用次数时替代）', labeled)
  self.assertNotIn("text:'引用次数'", labeled)
if __name__=='__main__':unittest.main()
