from dataclasses import replace
from pathlib import Path
import shutil

from app.geoip import GeoIpManager


def test_real_mmdb_reader_path(settings, tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures/GeoIP2-City-Test.mmdb"
    target = tmp_path / "geoip/test.mmdb"
    target.parent.mkdir(parents=True)
    shutil.copyfile(fixture, target)
    manager = GeoIpManager(replace(settings, geoip_db_path=target))
    assert manager.open_existing() is True
    record = manager.lookup("81.2.69.160")
    assert record["country"]["iso_code"] == "GB"
    assert record["location"]["latitude"] == 51.5142
    manager.close()
