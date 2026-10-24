import io

import tuners

A, B = "192.168.1.50", "192.168.1.51"


def _status(*channels):
    """status.json for a box whose tuners are on these channels ('' = free)"""
    return [{"Resource": f"tuner{i}", "VctNumber": ch, "VctName": "X" if ch else ""} for i, ch in enumerate(channels)] + \
        [{"Resource": "net"}]


def test_parse_addresses():
    assert tuners.parse_addresses("") == []
    assert tuners.parse_addresses(A) == [A]
    assert tuners.parse_addresses(f" {A},{B} ; {A}") == [A, B]
    assert tuners.parse_addresses([A, B]) == [A, B]


def test_merge_lineups():
    channels, carriers = tuners.merge_lineups([
        (A, [{"GuideNumber": "24.1", "GuideName": "KVUE"}, {"GuideNumber": "7.1", "GuideName": "KTBC"}]),
        (B, [{"GuideNumber": "24.1", "GuideName": "KVUE-DT"}, {"GuideNumber": "4.1", "GuideName": "WIVB"}]),
        ("192.168.1.52", None),  # didn't answer
    ])
    assert channels == {"24.1": "KVUE", "7.1": "KTBC", "4.1": "WIVB"}  # the first box's name wins
    assert carriers == {"24.1": [A, B], "7.1": [A], "4.1": [B]}


def test_tuner_numbers_run_across_boxes_and_survive_a_box_going_down():
    counts = {}
    pool, down = tuners.combine_status([(A, _status("24.1", "")), (B, _status("", "", ""))], counts,
                                       ours={(A, "24.1")})
    assert [(t["index"], t["box"], t["box_index"]) for t in pool] == \
        [(0, A, 0), (1, A, 1), (2, B, 0), (3, B, 1), (4, B, 2)]
    assert pool[0]["ours"] and not down and counts == {A: 2, B: 3}
    # Box 1 stops answering: box 2's tuners keep their numbers
    pool, down = tuners.combine_status([(A, None), (B, _status("", "7.1", ""))], counts)
    assert [t["index"] for t in pool] == [2, 3, 4] and down == [A]
    assert tuners.combine_status([(A, None), (B, None)], counts) == (None, [A, B])


def test_box_order_prefers_free_tuners():
    carriers = {"24.1": [A, B], "7.1": [A]}
    pool, _ = tuners.combine_status([(A, _status("4.1", "")), (B, _status("", ""))], {})
    assert tuners.box_order("24.1", carriers, pool) == [B, A]  # B has more free
    assert tuners.box_order("7.1", carriers, pool) == [A]  # only A has it
    pool, _ = tuners.combine_status([(A, _status("4.1", "")), (B, _status("4.1", "5.1"))], {})
    assert tuners.box_order("24.1", carriers, pool) == [A, B]
    assert tuners.box_order("24.1", carriers, None) == [A, B]  # unknown: configured order


def test_free_for_counts_only_boxes_with_the_channel():
    carriers = {"24.1": [A, B], "7.1": [A]}
    pool, _ = tuners.combine_status([(A, _status("4.1", "5.1")), (B, _status("", "9.1"))], {})
    assert tuners.free_for("7.1", carriers, pool) == (0, ["4.1 X", "5.1 X"])
    assert tuners.free_for("24.1", carriers, pool)[0] == 1
    assert tuners.free_for(None, carriers, pool)[0] == 1
    assert tuners.free_for("99.1", carriers, pool)[0] == 1  # not in any lineup: count every box


class BusyBox:
    """ffmpeg reading from a box: the first box answers 503 (its last tuner was just taken)"""
    runs = []

    def __init__(self, cmd, **kw):
        BusyBox.runs.append(cmd)
        busy = cmd[cmd.index("-i") + 1].startswith(f"http://{A}:")
        self.returncode = 1 if busy else 0
        self.stderr = io.BytesIO(b"HTTP error 503 Service Unavailable\n" if busy else b"")
        self.stdin, self.stdout = io.BytesIO(), None
        if not busy:
            with open(cmd[-1], "wb") as f:
                f.write(b"x" * 10)

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


def test_recording_moves_to_the_next_box_when_one_has_no_tuner(dvr, monkeypatch, tmp_path):
    BusyBox.runs = []
    monkeypatch.setattr(dvr.subprocess, "Popen", BusyBox)
    dvr.config.config.setdefault("recording", {}).update(captions=False)
    path = str(tmp_path / "Show.mp4")
    try:
        dvr._record_to_file("24.1", 30, 23, "fast", "mp4", "2026-10-28T19:30:00", path, [A, B])
    finally:
        dvr.config.config["recording"]["captions"] = True
    assert [r[r.index("-i") + 1] for r in BusyBox.runs] == [f"http://{A}:5004/auto/v24.1",
                                                           f"http://{B}:5004/auto/v24.1"]
    assert dvr.os.path.exists(path)
