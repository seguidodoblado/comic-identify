from comic_identify.settings import Settings
from comic_identify.theming import icon_choice, is_dark_theme, theme_variant


def test_theme_variant_keeps_the_accent_for_mint_and_follows_adwaita_yaru_for_the_rest():
    assert theme_variant("Mint-Y-Aqua", True) == "Mint-Y-Dark-Aqua"
    assert theme_variant("Mint-Y-Dark-Aqua", False) == "Mint-Y-Aqua"
    assert theme_variant("Mint-Y", True) == "Mint-Y-Dark" and theme_variant("Mint-Y-Dark", False) == "Mint-Y"
    assert theme_variant("Mint-Y-Dark-Aqua", True) == "Mint-Y-Dark-Aqua"          # ya oscuro: igual
    assert theme_variant("Mint-Y-Aqua", False) == "Mint-Y-Aqua"                    # ya claro: igual
    assert theme_variant("Adwaita", True) == "Adwaita-dark" and theme_variant("Yaru-blue-dark", False) == "Yaru-blue"
    assert theme_variant("Yaru-blue", True) == "Yaru-blue-dark"


def test_is_dark_theme():
    assert is_dark_theme("Mint-Y-Dark-Aqua") and is_dark_theme("Adwaita-dark") and is_dark_theme("Yaru-DARK")
    assert not is_dark_theme("Mint-Y-Aqua") and not is_dark_theme("") and not is_dark_theme(None)


def _theme(*icons):
    return lambda name: name in icons


def test_icon_choice_is_symbolic_in_dark_and_colored_in_light_when_the_theme_has_both():
    both = _theme("document-open", "document-open-symbolic", "folder-open-symbolic")
    assert icon_choice(("document-open-symbolic", "folder-open-symbolic"), True, both) == "document-open-symbolic"
    assert icon_choice(("document-open-symbolic", "folder-open-symbolic"), False, both) == "document-open"
    assert icon_choice(("document-open",), True, both) == "document-open-symbolic"       # con o sin «-symbolic» en la petici\xf3n


def test_icon_choice_falls_back_to_the_other_variant_then_to_the_next_name_then_to_nothing():
    only_symbolic = _theme("pan-down-symbolic", "edit-paste-symbolic")
    assert icon_choice(("pan-down-symbolic",), False, only_symbolic) == "pan-down-symbolic"    # sin color: la simb\xf3lica
    only_color = _theme("emblem-ok")
    assert icon_choice(("emblem-ok-symbolic",), True, only_color) == "emblem-ok"              # sin simb\xf3lica: la de color
    mixed = _theme("object-select-symbolic")
    assert icon_choice(("emblem-ok-symbolic", "object-select-symbolic"), True, mixed) == "object-select-symbolic"
    assert icon_choice(("nada-symbolic",), True, mixed) == "" and icon_choice((), False, mixed) == ""


def test_icon_choice_uses_a_symbolic_alternative_for_colored_icons_the_theme_lacks_in_symbolic():
    yaru = _theme("applications-internet", "network-workgroup-symbolic")
    assert icon_choice(("applications-internet-symbolic",), True, yaru) == "network-workgroup-symbolic"
    assert icon_choice(("applications-internet-symbolic",), False, yaru) == "applications-internet"


def test_the_chosen_theme_is_persisted_in_the_config_and_unset_means_follow_the_system(tmp_path):
    path = tmp_path / "config.json"
    assert Settings.load(path).dark_mode is None
    Settings(dark_mode=True).save(path)
    assert Settings.load(path).dark_mode is True
    Settings(dark_mode=False).save(path)
    assert Settings.load(path).dark_mode is False
    path.write_text('{"dark_mode": "si"}')
    assert Settings.load(path).dark_mode is None                                        # un valor raro se ignora
    path.write_text('{"api_key": "x"}')
    assert Settings.load(path).dark_mode is None
