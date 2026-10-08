#!/usr/bin/env python3
"""Render approved report layout using verified inputs; never recalculate source statistics (engagement charts may be derived from per-sample data only when their series are missing)."""
import argparse, html, json, re, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def esc(v): return html.escape(str(v))
def js(v): return json.dumps(v,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
def render_case(c, samples, media, detailed=True):
    assert type(c['rank']) is int and c['rank'] > 0, 'Case rank must be a positive integer'
    prefix=('video-case-' if detailed else 'video-copy-')+str(c['rank'])
    r=samples[c['rank']]
    field=c['source_field']; assert field in ('original_desc','transcript','image_text'), 'Invalid copy source'
    source=r.get(field); assert source, f'Missing {field} for {c["rank"]}'
    assert c['paragraphs'] and re.sub(r'\s+', '', ''.join(p['text'] for p in c['paragraphs']))==re.sub(r'\s+', '', str(source)), 'Paragraph text must preserve complete source, including punctuation'
    if field=='transcript': assert r.get('transcript_status') in ('verified','pending'), 'Selected transcript needs an explicit review status'
    review = '<p id="'+prefix+'-review">自动转写，待核对</p>' if field=='transcript' and r.get('transcript_status')=='pending' else ''
    paras=''.join('<div class="annotated-paragraph"><p class="original-paragraph">'+esc(p['text'])+'</p><aside class="margin-note"><strong>'+esc(p['point'])+'</strong><p>'+esc(p['note'])+'</p></aside></div>' for p in c['paragraphs'])
    frames=''
    if detailed:
        assert c.get('frames'), 'Detailed case needs real frames'
        for index,f in enumerate(c['frames'],1):
            path=Path(f['file']); assert not path.is_absolute() and '..' not in path.parts
            assert (media/path).is_file(), f'Missing frame: {path}'
            assert f.get('source_ref'), 'Frame needs source record'
            frames+='<figure class="image-strip-item"><button class="thumb" type="button" data-src="images/'+esc(path)+'" data-title="'+esc(r['title'])+'" data-sub="'+esc(f['label'])+'"><img id="'+prefix+'-frame-'+str(index)+'" src="images/'+esc(path)+'" alt="'+esc(f['label'])+'"></button><figcaption>'+esc(f['label'])+'</figcaption></figure>'
    cite_label=' · 引用次数暂未获取' if r.get('cite_count') is None else ' · 引用 '+esc(r.get('cite_count'))+' 次'
    return '<article id="'+prefix+'" class="content-part copy-study">'+review+'<div class="case-kicker">'+esc(r.get('content_type',''))+cite_label+'</div><h3>'+esc(c['heading'])+'</h3><p><a href="#s'+str(c['rank'])+'">'+esc(r['title'])+'</a></p>'+('<div class="video-frame-strip">'+frames+'</div>' if frames else '')+'<section class="case-original annotated-original"><h4>'+esc({'original_desc':'发布文案全文','transcript':'口播文案全文','image_text':'图片文字全文'}[field])+'</h4><div class="annotation-labels"><span>完整文案</span><span>写法批注</span></div><div id="'+prefix+'-text" class="annotated-copy">'+paras+'</div></section></article>'
def _metric_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value
def _engagement(row, valid_key, raw_key):
    return _metric_number(row.get(valid_key, row.get(raw_key)))
def _y_value(row, metric):
    if metric == 'cite':
        return _metric_number(row.get('cite_count'))
    if row.get('q_count') is not None:
        return _metric_number(row.get('q_count'))
    return _metric_number(row.get('question_count'))
def _series_blank(series, field):
    if not series:
        return True
    return all(item.get(field) is None for item in series)
def _cite_bucket(value):
    if value < 1000: return '<1千'
    if value < 10000: return '1千-1万'
    if value < 100000: return '1万-10万'
    return '≥10万'
def chart_fallback(stats, data):
    if any(row.get('cite_count') is not None for row in data):
        metric = 'cite'
    elif any(row.get('q_count') is not None or row.get('question_count') is not None for row in data):
        metric = 'q'
    else:
        return None
    def y(row):
        return _y_value(row, metric)
    if _series_blank(stats.get('scatter'), 'cite') and any((_engagement(row, 'digg_valid', 'digg_count') or 0) > 0 for row in data):
        stats['scatter'] = [
            {'digg': digg, 'cite': yy, 'rank': row.get('rank'), 'title': row.get('title')}
            for row in data
            for digg in [_engagement(row, 'digg_valid', 'digg_count')]
            for yy in [y(row)]
            if digg is not None and digg > 0 and yy is not None
        ]
    order = ('<1千', '1千-1万', '1万-10万', '≥10万')
    for key, valid_key, raw_key in (
        ('follower_vs_cite', 'follower_valid', 'follower_count'),
        ('digg_vs_cite', 'digg_valid', 'digg_count'),
        ('collect_vs_cite', 'collect_valid', 'collect_count'),
    ):
        if not _series_blank(stats.get(key), 'avg_cite'):
            continue
        if not any(_engagement(row, valid_key, raw_key) is not None for row in data):
            continue
        groups = {name: [] for name in order}
        for row in data:
            value = _engagement(row, valid_key, raw_key)
            yy = y(row)
            if value is None or yy is None:
                continue
            groups[_cite_bucket(value)].append(yy)
        stats[key] = [
            {'bucket': name, 'n': len(groups[name]), 'avg_cite': round(sum(groups[name]) / len(groups[name]), 1)}
            for name in order if groups[name]
        ]
    stats.setdefault('meta', {})['chart_y_metric'] = 'question_count' if metric == 'q' else 'citation_count'
    return metric
def _relabel_chart_axes(result):
    pairs = (
        ("text:'引用次数'", "text:'覆盖问题数（缺引用次数时替代）'"),
        ('纵轴引用次数', '纵轴覆盖问题数（缺引用次数时替代）'),
        ("label: '平均每条被引用次数'", "label: '平均每条覆盖问题数'"),
        ("text:'平均每条被引用次数（次/条）'", "text:'平均每条覆盖问题数（道/条）'"),
        ('`平均每条被引用 ${c.parsed.y} 次`', '`平均每条覆盖 ${c.parsed.y} 道问题`'),
    )
    for old, new in pairs:
        assert result.count(old) >= 1, old
        result = result.replace(old, new)
    return result
def build(manifest, output):
    report=json.loads(manifest.read_text()); stats=report['stats']; data=report['data']; meta=stats['meta']; samples={r['rank']:r for r in data}
    chart_metric=chart_fallback(stats, data)
    assert len(samples)==len(data)==meta['sample_n'], 'Sample counts do not match'
    assert report['client'].strip() and len(report['findings'])==5
    assert report['cases'] and report['copy_examples'], 'Case and copy analyses are required'
    media=(manifest.parent/report['images_dir']).resolve(); assert media.is_dir()
    for r in data:
        assert r.get('video_id') and r.get('url') and r.get('title')
        if r.get('transcript'): assert r.get('transcript_status') in ('verified','pending'), 'Every transcript needs an explicit review status'
        for f in r.get('images',[]):
            rel=Path(f);assert not rel.is_absolute() and '..' not in rel.parts and (media/rel).is_file(), f'Missing/unsafe sample image: {f}'
    for group in ('cases','copy_examples'):
        ranks=[c['rank'] for c in report[group]]
        assert len(ranks)==len(set(ranks)), 'Duplicate case ranks in '+group
    cases=''.join(render_case(c,samples,media) for c in report['cases'])
    copy=''.join(render_case(c,samples,media,False) for c in report['copy_examples'])
    vals={'CLIENT':esc(report['client']),'SECTOR':esc(meta['sector']),'DATE':esc(meta['monitor_date']),'PLATFORM':esc(meta['platform']),'SAMPLE_N':str(meta['sample_n']),'CITE_SUM':str(meta['cite_sum']),'QUESTION_N':str(meta.get('unique_questions','暂未获取')),'MAX_RATE':esc(str(meta['max_app_rate'])+'%' if meta.get('max_app_rate') is not None else '暂未获取'),'CASES_HTML':cases,'STATS_JSON':js(stats),'DATA_JSON':js(data),'REPORT_JSON':js({'copy_html':copy,'duration_reading':report['duration_reading']})}
    vals.update({'FINDING_'+str(i+1):esc(v) for i,v in enumerate(report['findings'])})
    template=(ROOT/'assets/template.html').read_text()
    result=re.sub(r'\{\{([A-Z_0-9]+)\}\}',lambda m:vals[m[1]],template)
    if chart_metric=='q': result=_relabel_chart_axes(result)
    assert not re.search(r'\{\{[A-Z_0-9]+\}\}',result)
    assert not output.exists(), 'Use a new output directory; do not overwrite an existing report'
    output.mkdir(parents=True)
    shutil.copytree(media,output/'images');shutil.copytree(ROOT/'assets/vendor',output/'vendor')
    (output/'index.html').write_text(result)
    print(output/'index.html')
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.input,a.out)
