import importlib.util
from pathlib import Path

import pytest

# Ausschnitt aus moOde 10.3.6, /var/www/inc/mpd.php (enhanceMetadata)
EXCERPT = (
    "\t\t\tif (substr($song['file'], 0, 4) == 'http') {\n"
    "\t\t\t\tif (isset($_SESSION[$song['file']])) {\n"
    "\t\t\t\t\t// Podcast\n"
    "\t\t\t\t\t$current['coverurl'] = LOGO_ROOT_DIR . $_SESSION[$song['file']]['name'] . \".jpg\";\n"
    "\t\t\t\t\t$current['artist'] = DEFAULT_STATION_NAME;\n"
    "\t\t\t\t\t$current['album'] = $_SESSION[$song['file']]['name'];\n"
    "\t\t\t\t} else {\n"
    "\t\t\t\t\t// UPnP file\n"
)


@pytest.fixture
def patch(tmp_path, monkeypatch):
    target = tmp_path / "mpd.php"
    target.write_text(
        "<?php\n" + EXCERPT + "// Radio\n$current['artist'] = DEFAULT_STATION_NAME;\n"
    )
    monkeypatch.setenv("MOODE_PATCH_TARGET", str(target))
    path = Path(__file__).resolve().parents[1] / "deploy" / "moode_patch.py"
    spec = importlib.util.spec_from_file_location("moode_patch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, target


def test_apply_changes_only_the_podcast_branch(patch):
    mod, target = patch
    before = target.read_text()
    assert mod.state(before) == "original"
    mod.apply()
    after = target.read_text()
    assert mod.state(after) == "applied"
    assert "$isEp && isset($song['Artist'])" in after
    # der Radio-Zweig (zweites DEFAULT_STATION_NAME) bleibt wie er war
    assert after.endswith("// Radio\n$current['artist'] = DEFAULT_STATION_NAME;\n")
    mod.apply()  # zweimal ist harmlos
    assert target.read_text() == after


def test_revert_restores_byte_for_byte(patch):
    mod, target = patch
    before = target.read_text()
    mod.apply()
    mod.revert()
    assert target.read_text() == before
    mod.revert()
    assert target.read_text() == before


def test_unknown_moode_version_is_left_alone(patch):
    mod, target = patch
    other = target.read_text().replace("// Podcast", "// Podcast (new moOde)")
    target.write_text(other)
    assert mod.state(other) == "unknown"
    mod.apply()
    assert target.read_text() == other
