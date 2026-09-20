import copy
import gzip
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, unquote

import pytest
from bs4 import BeautifulSoup
from edgefinance.core import digest, jsonfile, public_url
from edgefinance.analysis import (chunks, validate_extraction, validate_synthesis, evidence_bundle, job_id,
    _balanced_brief_evidence, _pack_records, synthesize_monthly_feature)
from edgefinance.collectors import parse_feed, parse_epo, financial_snapshot
from edgefinance.report import build_report, render_site, validate_report
from edgefinance.uspto import records, import_bulk, parse_patent


def test_versions_dedupe_retrieval_and_retain_original_bytes(project, document):
    s = project.store()
    first, new = s.add({**document, 'metadata':{'retrieved_vintage':'one'}}, b'raw original')
    same, repeated = s.add({**document, 'metadata':{'retrieved_vintage':'two'}}, b'different container bytes')
    assert new and not repeated and first['id'] == same['id']
    changed, _ = s.add({**document, 'text':'Changed value: 200 USD'}, b'raw changed')
    assert changed['document_id'] == first['document_id'] and changed['id'] != first['id']
    assert len(s.documents()) == 2 and len(s.documents(latest_only=True)) == 1
    assert gzip.decompress((project.data / first['raw_path']).read_bytes()) == b'raw original'
    s.close()


def test_chunks_cover_every_character():
    original = ('abcd中文\n'*1800) + 'tail'
    parts = chunks(original, 900)
    assert ''.join(p[1] for p in parts) == original
    assert all(original[a:b] == part for _,part,a,b in parts)
    assert all(parts[i][3] == parts[i+1][2] for i in range(len(parts)-1))


def test_hierarchical_packets_retain_every_evidence_record():
    records = [{"id": f"E-{i}", "statement": "x" * 80} for i in range(12)]
    packets = _pack_records(records, max_chars=280)
    assert [record for packet in packets for record in packet] == records
    assert len(packets) > 1


def test_final_hierarchical_selection_rotates_across_packets_and_purposes():
    evidence = [{"id": f"E-{i}", "statement": "x" * 80} for i in range(6)]
    briefs = [
        {"opportunity_evidence_ids": ["E-0", "E-1"], "risk_evidence_ids": ["E-2"], "counterevidence_ids": []},
        {"opportunity_evidence_ids": ["E-3"], "risk_evidence_ids": ["E-4"], "counterevidence_ids": ["E-5"]},
    ]
    selected = _balanced_brief_evidence(briefs, evidence, max_chars=10_000)
    assert {item["id"] for item in selected} == {item["id"] for item in evidence}
    constrained = _balanced_brief_evidence(briefs, evidence, max_chars=len(json.dumps(evidence[0])) * 2 + 10)
    assert constrained[0]["id"] == "E-0" and constrained[1]["id"] == "E-3"


def test_quote_validation_rejects_invention():
    result = {'summary':'test','facts':[{'statement':'test','quote':'Revenue is 100 USD','type':'source_statement','caution':''}],'novelty':'','limitations':[]}
    validate_extraction(result, 'Revenue is 100 USD in Q1.')
    result['facts'][0]['quote'] = 'Revenue is 999 USD'
    with pytest.raises(ValueError): validate_extraction(result, 'Revenue is 100 USD in Q1.')


def test_cutoff_and_latest_filing_preserve_periods():
    points = [dict(start='2025-01-01',end='2025-03-31',val=100,filed='2025-05-01',form='10-Q'),
        dict(start='2025-01-01',end='2025-03-31',val=110,filed='2026-05-01',form='10-Q'),
        dict(start='2025-01-01',end='2025-12-31',val=500,filed='2026-02-01',form='10-K')]
    data={'facts':{'us-gaap':{'Revenues':{'units':{'USD':points}}}}}
    assert [r['val'] for r in financial_snapshot(data,'2025-06-01')] == [100]
    assert {r['val'] for r in financial_snapshot(data,'2026-06-01')} == {110,500}


def test_feed_skips_undated_and_invalid_links():
    raw=b'<rss><channel><item><title>Valid</title><link>https://example.org/a</link><pubDate>Thu, 01 Jan 2026 10:00:00 GMT</pubDate></item><item><link>https://example.org/b</link></item><item><link>javascript:x</link><pubDate>2026-01-01</pubDate></item></channel></rss>'
    assert len(parse_feed(raw)) == 1


def test_epo_bibliography_not_mistaken_for_full_text():
    doc = parse_epo(b'<ep-patent-document doc-number="123"><B540><B541>en</B541><B542>Test invention</B542></B540></ep-patent-document>', 'https://example.org/EP123/document.xml','2026-01-01')
    assert doc['title'] == 'Test invention' and doc['coverage'] == 'bibliographic_only'


@pytest.mark.parametrize('url',['javascript:alert(1)','https://user:password@example.org','https://example.org/?api_key=abc','file:///private'])
def test_no_sensitive_public_urls(url):
    with pytest.raises(ValueError): public_url(url)


def patent(number):
    return f'''<?xml version="1.0"?><!DOCTYPE us-patent-grant SYSTEM "not-fetched.dtd"><us-patent-grant>
    <publication-reference><document-id><country>US</country><doc-number>{number}</doc-number><kind>B2</kind><date>20260106</date></document-id></publication-reference>
    <invention-title>Artificial test optical device</invention-title><assignees><assignee><addressbook><orgname>NVIDIA Corporation</orgname></addressbook></assignee></assignees>
    <abstract>Artificial optical device fixture, no real patent.</abstract><description>Test description</description><claims>Test claims</claims></us-patent-grant>'''.encode()


def test_bulk_concatenated_zip_resumes_without_duplicates(project, tmp_path):
    path = tmp_path / 'synthetic.zip'
    with zipfile.ZipFile(path,'w') as z: z.writestr('test.xml', patent('100')+patent('200')+patent('300'))
    a = import_bulk(project,path,max_records=1)
    assert a['cursor'] == 1 and a['status'] == 'partial'
    b = import_bulk(project,path,max_records=10)
    assert b['cursor'] == 3 and b['status'] == 'complete' and b['new_this_run'] == 2
    c = import_bulk(project,path)
    assert c['new_this_run'] == 0
    s=project.store(); docs=s.documents();s.close()
    assert len(docs)==3 and all(d['entities']==['NVDA'] for d in docs)


def test_truncated_bulk_is_not_marked_complete():
    with pytest.raises(ValueError): list(records(io.BytesIO(patent('100')+b'<us-patent-grant>unfinished')))


def test_bulk_xml_external_entity_is_never_expanded(project):
    raw=b'<us-patent-grant><invention-title>&external;</invention-title></us-patent-grant>'
    with pytest.raises(Exception): parse_patent(raw,'https://example.org',project)


def test_future_bulk_is_left_pending(project,tmp_path):
    p=tmp_path/'future.xml';p.write_bytes(patent('100').replace(b'20260106',b'20350106'))
    r=import_bulk(project,p,as_of='2026-01-01')
    assert r['cursor']==0 and r['status']=='awaiting_publication_date'


def test_report_export_build_and_all_relative_links(project,document):
    s=project.store();s.add({**document,'title':'<script>alert(1)</script>'},b'original');s.close()
    r=build_report(project,'2026-01-02',use_codex=False)
    out=render_site(project)
    assert r['coverage']['pending_chunks']==1 and not r['theses']
    assert (out/'data/v1/latest.json').exists()
    assert (out/'features.html').exists() and (out/'assets/yabilab-logo.png').exists()
    assert '每月第一週' in (out/'features.html').read_text(encoding='utf-8')
    assert '<script>alert(1)</script>' not in (out/'sources.html').read_text(encoding='utf-8')
    for file in out.glob('*.html'):
        soup=BeautifulSoup(file.read_text(encoding='utf-8'),'html.parser')
        for node in soup.select('a[href],link[href],script[src]'):
            target=node.get('href',node.get('src','')); parsed=urlsplit(target)
            if parsed.scheme or parsed.netloc: continue
            dest=file.parent/unquote(parsed.path) if parsed.path else file
            assert dest.exists(), (file.name,target)
            if parsed.fragment and dest.suffix=='.html':
                dest_soup=BeautifulSoup(dest.read_text(encoding='utf-8'),'html.parser')
                assert dest_soup.find(id=parsed.fragment),target
    assert render_site(project,from_public=True)==out
    latest=json.loads((project.root/'public-data/v1/latest.json').read_text())
    rp=project.root/'public-data/v1'/Path(latest['manifest']).parent/'report.json'
    rp.write_text('{}')
    with pytest.raises(ValueError): render_site(project,from_public=True)


def test_dangling_citations_and_raw_text_rejected(project,document):
    s=project.store();s.add(document,b'raw');s.close()
    r=build_report(project,'2026-01-02',False)
    r['risks'][0]['evidence_ids']=['made-up']
    with pytest.raises(ValueError): validate_report(r)


def test_missing_keys_are_explicit_not_mock_data(project):
    from edgefinance.collectors import collect
    project.sources=[{'id':'needs-key','name':'test','kind':'fred','enabled':True,'credential':'MISSING_TEST_KEY'}]
    result=collect(project,'2026-01-02')
    assert result['status']=='partial' and result['sources'][0]['status']=='needs_credentials'
    assert not result['new_document_ids']


def test_failed_rss_full_text_keeps_retry_queue(project,monkeypatch):
    from edgefinance import collectors
    project.sources=[{'id':'rss-test','name':'RSS','kind':'rss','enabled':True,'url':'https://example.org/feed'}]
    def get(self,url,**kwargs):
        if url.endswith('/feed'):
            return b'<rss><channel><item><title>Test</title><link>https://example.org/article</link><pubDate>2026-01-01</pubDate><description>Only feed summary</description></item></channel></rss>','text/xml'
        raise TimeoutError()
    monkeypatch.setattr(collectors.Fetcher,'get',get)
    r=collectors.collect(project,'2026-01-02')
    assert r['status']=='partial'
    assert len(json.loads((project.data/'queues/rss-test.json').read_text()))==1
    s=project.store();assert s.documents()[0]['coverage']=='feed_summary';s.close()


def test_complete_analysis_is_reused_without_calling_codex(project,document,monkeypatch):
    from edgefinance import analysis
    s=project.store();doc,_=s.add(document,b'raw')
    job=job_id(doc,0,doc['text'],'')
    s.save_analysis(job,doc['id'],0,'complete',{'result':{'summary':'test','facts':[],'novelty':'','limitations':[]}})
    s.close()
    monkeypatch.setattr(analysis,'CodexRunner',lambda _: (_ for _ in ()).throw(AssertionError('must not call')))
    assert analysis.analyze(project,'2026-01-02')['pending_before']==0


def test_bls_missing_values_retained_as_gaps(project,monkeypatch):
    from edgefinance import collectors
    project.sources=[{'id':'bls','name':'BLS','kind':'bls','enabled':True,'series':[{'id':'TEST','name':'Synthetic','unit':'percent'}]}]
    payload={'status':'REQUEST_SUCCEEDED','Results':{'series':[{'data':[
        {'year':'2026','period':'M01','value':'4.1','footnotes':[]},
        {'year':'2025','period':'M10','value':'-','footnotes':[{'text':'Missing'}]},
        {'year':'2025','period':'M13','value':'4.2','footnotes':[]}]}]}}
    monkeypatch.setattr(collectors.Fetcher,'get',lambda *a,**kw:(json.dumps(payload).encode(),'application/json'))
    r=collectors.collect(project,'2030-01-01');assert r['sources'][0]['fetched']==1
    s=project.store();doc=s.documents()[0];s.close()
    assert len(doc['metadata']['observations'])==1
    assert doc['metadata']['missing_observations'][0]['date']=='2025-10-01'


def test_site_failure_keeps_previous_build(project,document,monkeypatch):
    from edgefinance import report
    s=project.store();s.add(document,b'raw');s.close()
    build_report(project,'2026-01-02',False);out=render_site(project)
    original=(out/'index.html').read_bytes()
    def broken(*a,**k): raise RuntimeError('test forced render failure')
    monkeypatch.setattr(report.Environment,'get_template',broken)
    with pytest.raises(RuntimeError):render_site(project)
    assert (out/'index.html').read_bytes()==original


def test_company_without_mapped_evidence_is_rejected(project):
    risk=lambda h:dict(horizon_days=h,title='test',assessment='unknown',rationale='test',evidence_ids=[],transmission='test',triggers=[],easing_conditions=[],limitations=[])
    thesis=dict(topic_id=project.topics[0]['id'],title='test',statement='test',company_ids=['NVDA'],evidence_ids=['E-1'],counterevidence_ids=[],counterargument='test',value_capture='test',maturity='test',invalidation='test',next_check='test')
    result=dict(summary='test',theses=[thesis],risks=[risk(14),risk(30),risk(90),risk(180)],next_week=[],limitations=[])
    with pytest.raises(ValueError):validate_synthesis(result,[{'id':'E-1','entities':[]}],project)
    validate_synthesis(result,[{'id':'E-1','entities':['NVDA']}],project)


def test_monthly_feature_only_runs_in_first_week(project):
    assert synthesize_monthly_feature(project,[{'id':'E-1'}],[],'2026-09-20') is None


def test_public_export_rejects_path_traversal(project):
    r=build_report(project,'2026-01-02',False)
    r['companies'][0]['ticker']='../../private'
    with pytest.raises(ValueError):validate_report(r)


def test_frozen_report_not_overwritten_by_later_build(project):
    report=build_report(project,'2026-01-02',False);render_site(project)
    release=project.root/'public-data/v1/releases'/report['id']
    before={p.name:p.read_bytes() for p in release.glob('*.json')}
    build_report(project,'2026-01-03',False);render_site(project)
    assert before=={p.name:p.read_bytes() for p in release.glob('*.json')}


def test_same_day_revisions_publish_only_latest_weekly_edition(project):
    first=build_report(project,'2026-01-02',False)
    second=build_report(project,'2026-01-02',False)
    out=render_site(project)
    archive=BeautifulSoup((out/'archive.html').read_text(encoding='utf-8'),'html.parser')
    links=[a['href'] for a in archive.select('.archive-list > a')]
    assert links == [f"report-{second['id']}.html"]
    assert not (project.root/'public-data/v1/releases'/first['id']).exists()


def test_failed_synthesis_preserves_previous_report(project,document,monkeypatch):
    from edgefinance import report
    from edgefinance.analysis import CodexError
    old=build_report(project,'2026-01-01',False)
    monkeypatch.setattr(report,'evidence_bundle',lambda *a:([{'id':'test'}],[],{'pending_chunks':0}))
    monkeypatch.setattr(report,'synthesize',lambda *a:(_ for _ in ()).throw(CodexError('simulated quota')))
    with pytest.raises(CodexError):build_report(project,'2026-01-02')
    s=project.store();assert [r['id'] for r in s.reports()]==[old['id']];s.close()
