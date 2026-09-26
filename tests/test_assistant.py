import pytest

from comic_identify import cli
from comic_identify.assistant import build_argv, build_prompt, prepare_workspace
from comic_identify.settings import Settings


def test_prompt_mentions_the_image_and_the_local_search():
    prompt = build_prompt("portada.png")
    assert "@portada.png" in prompt and "comic-identify buscar" in prompt and "{" not in prompt
    for site in ("Tebeosfera", "Whakoom", "Panini.es", "Norma", "fichas.universomarvel.com", "Zona Negativa"):
        assert site in prompt


def test_build_argv_substitutes_the_prompt_as_a_single_argument():
    assert build_argv("claude {prompt}", "hola mundo: `x`") == ["claude", "hola mundo: `x`"]
    assert build_argv("opencode --prompt {prompt}", "p") == ["opencode", "--prompt", "p"]
    assert build_argv("codex", "p") == ["codex"]          # sin {prompt}: se lanza tal cual
    assert build_argv('mi-cli --modelo "sonnet 5" {prompt}', "p") == ["mi-cli", "--modelo", "sonnet 5", "p"]
    with pytest.raises(ValueError):
        build_argv("   ", "p")
    with pytest.raises(ValueError):
        build_argv('claude "sin cerrar', "p")


def test_workspace_holds_only_the_current_cover(tmp_path):
    first, second = tmp_path / "a.PNG", tmp_path / "b.jpg"
    first.write_bytes(b"uno")
    second.write_bytes(b"dos")
    work = tmp_path / "ai"
    prepare_workspace(first, work)
    assert [p.name for p in work.iterdir()] == ["portada.png"]
    prepare_workspace(second, work)
    assert [p.name for p in work.iterdir()] == ["portada.jpg"] and (work / "portada.jpg").read_bytes() == b"dos"


def test_settings_keep_the_assistant_command(tmp_path):
    file = tmp_path / "config.json"
    assert Settings.load(file).assistant == "claude {prompt}"
    Settings("k", [], "opencode --prompt {prompt}").save(file)
    assert Settings.load(file).assistant == "opencode --prompt {prompt}"


def test_buscar_command(index, tmp_path, monkeypatch, capsys):
    assert cli.buscar([]) == 2 and "Uso:" in capsys.readouterr().err

    monkeypatch.setattr(cli, "GCD_DB", index.path)
    assert cli.buscar(["spiderman", "12"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Spiderman #12 | Panini España") and lines[0].endswith("/issue/100/")
    assert cli.buscar(["xyzzy"]) == 0 and capsys.readouterr().out.strip() == "Sin resultados."

    monkeypatch.setattr(cli, "GCD_DB", tmp_path / "no_existe.db")
    assert cli.buscar(["spiderman"]) == 1 and "No hay índice" in capsys.readouterr().err


def test_dispatch_never_opens_the_gui_for_unknown_commands(tmp_path, capsys):
    cover = tmp_path / "portada.png"
    cover.write_bytes(b"x")
    assert cli.dispatch([]) is None
    assert cli.dispatch([str(cover)]) == cover

    for args in (["--help"], ["-h"], ["help"]):
        with pytest.raises(SystemExit) as exit_info:
            cli.dispatch(args)
        assert exit_info.value.code == 0 and "comic-identify buscar" in capsys.readouterr().out

    for args in (["search", "batman"], ["--version"], [str(tmp_path / "no_existe.png")], [str(cover), "otro"]):
        with pytest.raises(SystemExit) as exit_info:      # antes: abría la interfaz y duplicaba la ventana
            cli.dispatch(args)
        assert exit_info.value.code == 2 and "Orden no reconocida" in capsys.readouterr().err

    with pytest.raises(SystemExit) as exit_info:
        cli.dispatch(["buscar"])
    assert exit_info.value.code == 2 and "Uso:" in capsys.readouterr().err


def test_settings_keep_the_naming_pattern(tmp_path):
    file = tmp_path / "config.json"
    assert Settings.load(file).pattern == "{nombre} {volumen} {bandera} [{contenido}] ({edicion}) - {sello}"
    Settings("k", [], "claude {prompt}", "{nombre} {numero}").save(file)
    assert Settings.load(file).pattern == "{nombre} {numero}"
