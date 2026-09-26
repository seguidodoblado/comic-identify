from comic_identify.collection import SeriesReport, build_series, ranges

FOLDER = "/c/Capitán Marvel 🇪🇸 [1999-2001] - Forum"


def row(name, series="", volume="", number="", count=None, category="", tagged=0, folder=FOLDER):
    return (f"{folder}/{name}", series, volume, number, count, category, tagged)


def test_ranges_groups_consecutive_numbers_and_truncates():
    assert ranges([3, 7, 13, 14, 15, 36]) == "3, 7, 13-15, 36"
    assert ranges([]) == "" and ranges([5]) == "5"
    long = ranges(list(range(2, 400, 2)))
    assert long.endswith("…") and len(long) <= 112


def test_untagged_files_in_a_normalized_folder_use_the_number_in_their_name():
    rows = [row(f"Capitán Marvel 🇪🇸 [1999-2001] - Forum #{n:02d}.cbz") for n in (1, 2, 4, 7)]
    (report,) = build_series(rows)
    assert report.name == "Capitán Marvel 🇪🇸 [1999-2001] - Forum" and report.files == 4 and report.tagged == 0
    assert report.owned == [1, 2, 4, 7] and report.count is None
    assert report.missing == [3, 5, 6] and report.status == "incompleta"       # huecos entre los que hay


def test_the_count_from_the_metadata_defines_the_expected_total():
    rows = [row(f"x{n}.cbz", "Capitán Marvel", "", str(n), 6, "Series", 1) for n in (1, 2, 3)]
    (report,) = build_series(rows)
    assert report.count == 6 and report.missing == [4, 5, 6] and report.category == "Series"
    assert report.tagged == 3 and report.status == "incompleta"
    full = build_series([row(f"x{n}.cbz", "S", "", str(n), 3, "", 1) for n in (1, 2, 3)])[0]
    assert full.missing == [] and full.status == "completa"
    open_ended = build_series([row(f"x{n}.cbz", "S", "", str(n), None, "", 1) for n in (1, 2, 3)])[0]
    assert open_ended.status == "sin total"


def test_numbers_beyond_the_count_are_strays_and_a_zero_issue_counts():
    report = build_series([row(f"x{n}.cbz", "S", "", str(n), 2, "", 1) for n in (0, 1, 2, 5)])[0]
    assert report.strays == [5] and report.total == 2 and report.missing == [] and report.status == "completa"
    assert build_series([row("a.cbz", "S", "", "1", 2, "", 1)])[0].missing == [2]


def test_duplicates_and_non_integer_numbers_are_reported_separately():
    rows = [row("a.cbz", "S", "", "1", 3, "", 1), row("b.cbz", "S", "", "1", 3, "", 1),
            row("c.cbz", "S", "", "Annual 1", 3, "", 1), row("d.cbz", "S", "", "2", 3, "", 1),
            row("e.cbz", "S", "", "3", 3, "", 1)]
    (report,) = build_series(rows)
    assert report.duplicated == [1] and report.other == 1 and report.missing == [] and report.files == 5


def test_untagged_files_in_a_loose_folder_do_not_form_a_series():
    loose = [row(f"Algo {n}.cbz", folder="/c/00 - Por colocar") for n in (1, 5, 9)]
    assert build_series(loose) == []
    tagged = [row("a.cbz", "Serie X", "", "1", 2, "", 1, folder="/c/00 - Por colocar")]
    assert [r.name for r in build_series(tagged)] == ["Serie X"]          # con metadatos sí, esté donde esté


def test_series_are_split_by_folder_and_volume_and_sorted_naturally():
    rows = [row("a.cbz", "Batman", "10", "1", 1, "", 1), row("b.cbz", "Batman", "2", "1", 1, "", 1),
            row("c.cbz", "Batman", "2", "1", 1, "", 1, folder="/otra")]
    assert [(r.name, r.folder) for r in build_series(rows)] == [
        ("Batman Volumen 2", FOLDER), ("Batman Volumen 2", "/otra"), ("Batman Volumen 10", FOLDER)]
    assert isinstance(build_series(rows)[0], SeriesReport)


def test_without_a_total_only_the_holes_between_owned_numbers_count():
    (report,) = build_series([row(f"x{n}.cbz", "S", "", str(n), None, "", 1) for n in (16, 17, 19)])
    assert report.missing == [18] and report.starts_at == 16 and report.status == "incompleta"
    with_count = build_series([row(f"x{n}.cbz", "S", "", str(n), 20, "", 1) for n in (16, 17, 19)])[0]
    assert with_count.missing == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 20]      # con total, todo lo que falta
    assert with_count.starts_at == 16
    assert build_series([row("a.cbz", "S", "", "1", None, "", 1)])[0].starts_at is None


def test_a_normalized_folder_without_metadata_and_repeated_numbers_is_a_mix_of_series():
    names = ["Judgment Day 1", "Judgment Day 2", "Avengers 1", "X-Men 2", "X-Men 3"]
    (report,) = build_series([row(f"{n}.cbz") for n in names])
    assert report.mixed and report.status == "mezcla" and report.missing == [] and report.duplicated == [1, 2]
    tagged = build_series([row(f"{n}.cbz", "Judgment Day", "", str(i), 5, "", 1) for i, n in enumerate(names, 1)])
    assert not tagged[0].mixed and tagged[0].missing == []


def test_untagged_files_join_the_only_tagged_series_of_their_folder():
    rows = [row("a.cbz", "Capitán Marvel", "", "1", 4, "", 1), row("b.cbz", "Capitán Marvel", "", "2", 4, "", 1),
            row("Capitán Marvel 🇪🇸 [1999-2001] - Forum #03.cbz")]
    (report,) = build_series(rows)
    assert report.name == "Capitán Marvel" and report.files == 3 and report.tagged == 2
    assert report.owned == [1, 2, 3] and report.missing == [4]
    two = build_series([*rows[:2], row("c.cbz", "Otra", "", "1", 1, "", 1), rows[2]])
    assert sorted(r.name for r in two) == sorted(["Capitán Marvel", "Otra", "Capitán Marvel 🇪🇸 [1999-2001] - Forum"])


def test_an_isolated_number_far_from_the_run_is_a_stray_not_eighty_holes():
    numbers = [*range(1, 47), 129]                                  # El Castigador con un Spiderman #129 dentro
    (report,) = build_series([row(f"Capitán Marvel 🇪🇸 [1999-2001] - Forum #{n:03d}.cbz") for n in numbers])
    assert report.strays == [129] and report.missing == [] and report.total == 46 and not report.sparse
    holes = build_series([row(f"Capitán Marvel 🇪🇸 [1999-2001] - Forum #{n:03d}.cbz") for n in (*range(1, 20), 22, 129)])[0]
    assert holes.strays == [129] and holes.missing == [20, 21]      # los huecos reales siguen saliendo


def test_scattered_numbers_without_a_total_are_not_reported_as_gaps():
    rows = [row(f"Capitán Marvel 🇪🇸 [1999-2001] - Forum #{n:03d}.cbz") for n in (64, 87, 116, 130)]
    (report,) = build_series(rows)
    assert report.sparse and report.missing == [] and report.status == "sin total" and report.starts_at == 64
    tagged = build_series([row(f"x{n}.cbz", "S", "", str(n), 200, "", 1) for n in (64, 87, 116)])[0]
    assert not tagged.sparse and tagged.missing[0] == 1          # con total sí: falta casi todo, y se dice
