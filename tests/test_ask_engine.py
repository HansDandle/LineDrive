import ask_engine as a


def ask(guide, question, **kw):
    return a.answer(question, guide["programs"], guide["lineup"], now=guide["now"], **kw)


def test_next_basketball_game(guide):
    r = ask(guide, "when's the next basketball game?")
    assert r["programs"][0]["title"] == "WNBA Basketball"
    assert r["message"].startswith("Next basketball game: WNBA Basketball")
    assert "Tomorrow 1:00 PM" in r["message"]


def test_show_not_on_tomorrow_says_when_it_is(guide):
    r = ask(guide, "is jeopardy on tomorrow")
    assert r["message"].startswith("Jeopardy! isn't on tomorrow. Next airing:")
    assert all(p["title"] == "Jeopardy!" for p in r["programs"])


def test_title_with_day_words_is_a_title_not_a_time(guide):
    r = ask(guide, "when is saturday night live")
    assert [p["title"] for p in r["programs"]] == ["Saturday Night Live"]
    assert "Tonight 10:29 PM" in r["message"]


def test_network_and_clock_time(guide):
    r = ask(guide, "what's on nbc tonight at 9")
    assert r["message"] == "On NBC at 9:00 PM tonight: College Football (Oregon at USC) on 36.1 KXAN-DT."


def test_what_is_on_at_a_time_lists_everything_airing_then(guide):
    r = ask(guide, "what's on at 8")
    assert r["total"] >= 5
    assert all(p["start"] <= guide["now"].replace(hour=20, minute=0).timestamp() < p["end"] for p in r["programs"])


def test_simulcasts_merge_into_one_card(guide):
    r = ask(guide, "when is the next football game")
    first = r["programs"][0]
    assert first["title"] in ("College Football", "NFL Football")
    assert len({(p["title"], p["episode_title"], p["start"]) for p in r["programs"]}) == len(r["programs"])


def test_distant_channel_ranks_after_local(guide):
    r = ask(guide, "when is jeopardy", distant={"5.1"})
    assert r["programs"][0]["channel_number"] != "5.1"


def test_bare_words_need_a_title_match_or_return_none(guide):
    assert ask(guide, "hello there", strict=True) is None
    r = ask(guide, "jeopardy", strict=True)
    assert r and r["programs"][0]["title"] == "Jeopardy!"


def test_not_a_question(guide):
    # Plain words are asked in strict mode by the app; no title match -> None (the app shows help)
    assert ask(guide, "thanks", strict=True) is None
    assert ask(guide, "thanks")["programs"] == []


def test_abbreviations(guide):
    r = ask(guide, "when is snl")
    assert r["programs"][0]["title"] == "Saturday Night Live"


def test_record_prefix_is_ignored_for_search(guide):
    assert ask(guide, "record the next basketball game")["programs"][0]["title"] == "WNBA Basketball"


def test_parse_when_windows(guide):
    now = guide["now"]
    mode, start, end, label, rest = a.parse_when("what's on tomorrow night", now)
    assert (mode, label, start.hour, start.day) == ("range", "tomorrow night", 17, now.day + 1)
    mode, at, _, label, _ = a.parse_when("at 8", now)
    assert (mode, at.hour, label) == ("at", 20, "at 8:00 PM tonight")
    mode, at, _, _, _ = a.parse_when("at 7 am", now)
    assert at.hour == 7 and at.day == now.day + 1   # 7 AM already passed today
