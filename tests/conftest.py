from pathlib import Path
import shutil
import pytest
from edgefinance.core import Project

@pytest.fixture
def project(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / 'config', tmp_path / 'config')
    p = Project(tmp_path)
    p.secrets = {}
    return p

@pytest.fixture
def document():
    return {'source_id':'fixture','url':'https://example.org/source','title':'Test fixture',
        'published_at':'2026-01-01','text':'Revenue is 100 USD in this deliberately synthetic test fixture.'}
