import pytest

from tomits.db import make_session_factory


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def session(db_file):
    Session = make_session_factory(db_file)
    with Session() as s:
        yield s
