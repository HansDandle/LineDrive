import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def guide():
    """A fixed week of real over-the-air listings (Austin, TX, Sept 26 - Oct 2 2026)"""
    data = json.load(open(ROOT / "tests" / "fixtures" / "guide_sample.json", encoding="utf-8"))
    data["now"] = datetime.fromisoformat(data["now"])
    return data


@pytest.fixture(scope="session")
def dvr(tmp_path_factory):
    """The dvr_web module, loaded with an empty config in a scratch folder (no tuner needed)"""
    work = tmp_path_factory.mktemp("linedrive")
    os.environ["LINEDRIVE_RECORDINGS"] = str(work / "recordings")
    os.chdir(work)
    import dvr_web
    return dvr_web
