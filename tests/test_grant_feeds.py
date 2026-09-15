import json
import pytest
from edgefinance.grant_feeds import epo_entries, epo_grants, uspto_grant_files
from edgefinance.collectors import Fetcher
from edgefinance.tipo import company_candidates, grant_issues, grant_page, roc_date


def test_epo_first_grants_and_changes_are_distinct():
    raw=b'<a href="/publication-server/rest/v1.2/patents/EP123NWA1">a</a><a href="/publication-server/rest/v1.2/patents/EP124NWB1">b</a><a href="/publication-server/rest/v1.2/patents/EP125NWB2">c</a><a href="/publication-server/rest/v1.2/patents/EP126NWB9">d</a>'
    entries=epo_entries(raw,'2026-09-09')
    assert len(entries)==3
    assert [e['event'] for e in entries]==['new_grant','amendment_or_correction','amendment_or_correction']


def test_grants_all_discovered_even_when_detail_budget_zero(project,monkeypatch):
    def get(self,url,**kw):
        if url.endswith('publication-dates'):
            return b'<a href="/publication-server/rest/v1.2/publication-dates/20260909/patents">2026/09/09</a>','text/html'
        return b'<a href="/publication-server/rest/v1.2/patents/EP124NWB1">b</a><a href="/publication-server/rest/v1.2/patents/EP125NWB2">c</a>','text/html'
    monkeypatch.setattr(Fetcher,'get',get)
    fetch=Fetcher(project);store=project.store();state={'failed':0}
    epo_grants(project,fetch,store,{},'2026-09-15',0,lambda *a:None,state)
    assert state['discovered']==2 and state['new_grants_discovered']==1 and state['pending_details']==2 and state['status']=='partial'
    epo_grants(project,fetch,store,{},'2026-09-15',0,lambda *a:None,state)
    feed=json.loads((project.data/'patent-feeds/epo-grants.json').read_text())
    assert len(feed['entries'])==2
    fetch.close();store.close()


def test_uspto_grant_batch_dates_not_catalog_modified_dates():
    payload={'bulkDataProductBag':[{'productFileBag':{'fileDataBag':[
        {'fileName':'ipg260908.zip','fileDownloadURI':'https://api.uspto.gov/api/v1/datasets/products/files/PTGRXML/ipg260908.zip'},
        {'fileName':'ipg260915.zip','fileDownloadURI':'https://api.uspto.gov/api/v1/datasets/products/files/PTGRXML/ipg260915.zip'},
        {'fileName':'ipa260910.zip','fileDownloadURI':'https://api.uspto.gov/api/v1/datasets/products/files/PTAPPXML/ipa260910.zip'}]}}]}
    files=uspto_grant_files(payload,'2026-09-08','2026-09-14')
    assert len(files)==1 and files[0]['grant_date']=='2026-09-08'


def test_uspto_download_must_not_send_api_key_elsewhere():
    with pytest.raises(ValueError):uspto_grant_files({'fileName':'ipg260908.zip','fileDownloadURI':'https://untrusted.example/file.zip'},'2026-09-08','2026-09-15')


def test_tipo_roc_dates_and_issue_schema():
    assert roc_date('115.09.11') == '2026-09-11'
    assert roc_date('1041218') == '2015-12-18'
    assert grant_issues([{'vol': 53, 'no': 26, 'publicationDate': '115.09.11'}]) == [
        {'vol': 53, 'no': 26, 'published_at': '2026-09-11'}]


def test_tipo_grant_page_keeps_all_bibliography_but_marks_candidates(project):
    project.companies[0]['aliases'].append('測試股份有限公司')
    payload = {'totalCount': 2, 'totalPages': 1, 'size': 2, 'data': [
        {'certificateNo': 'I939001', 'applicationNo': '115100001', 'title': '半導體散熱裝置',
         'inventors': ['甲'], 'applicants': ['測試股份有限公司'], 'agents': [],
         'pdfUrl': 'https://cloud.tipo.gov.tw/S220/downloads/patent/example.pdf', 'imageUrls': []},
        {'certificateNo': 'M939002', 'applicationNo': '115200002', 'title': '一般容器',
         'inventors': ['乙'], 'applicants': ['未對應公司'], 'agents': [],
         'pdfUrl': 'https://cloud.tipo.gov.tw/S220/downloads/patent/example2.pdf', 'imageUrls': []}]}
    rows = grant_page(payload, {'vol': 53, 'no': 26, 'published_at': '2026-09-11'}, project)
    assert len(rows) == 2
    assert rows[0]['topics'] == ['compute'] and rows[0]['entities'] == ['NVDA']
    assert rows[0]['detail_status'] == 'pending'
    assert rows[1]['detail_status'] == 'not_selected'


def test_tipo_rejects_non_official_download_host(project):
    payload = {'size': 1, 'data': [{'certificateNo': 'I1', 'applicationNo': '115100001',
        'title': '半導體', 'inventors': [], 'applicants': [], 'pdfUrl': 'https://example.org/file.pdf'}]}
    with pytest.raises(ValueError):
        grant_page(payload, {'vol': 53, 'no': 26, 'published_at': '2026-09-11'}, project)
