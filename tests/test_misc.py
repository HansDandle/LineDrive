import struct
import zlib

import hdhomerun_control as h
from media_requests import parse_download_request


def test_download_requests():
    assert parse_download_request("download dune") == ("dune", None, None)
    assert parse_download_request("get the movie heat") == ("heat", "movie", None)
    assert parse_download_request("download season 2 of the bear") == ("the bear", "tv", [2])
    assert parse_download_request("request seasons 1-3 of severance") == ("severance", "tv", [1, 2, 3])
    assert parse_download_request("what's on now") is None
    assert parse_download_request("record snl") is None


def test_control_packet_has_valid_crc():
    pkt = h._packet(h.TYPE_GETSET_REQ, h._tlv(h.TAG_GETSET_NAME, "/tuner0/channel"))
    body, crc = pkt[:-4], struct.unpack("<I", pkt[-4:])[0]
    assert crc == zlib.crc32(body) & 0xFFFFFFFF
    assert struct.unpack(">HH", body[:4]) == (h.TYPE_GETSET_REQ, len(body) - 4)


def test_tag_parsing_round_trip():
    payload = h._tlv(h.TAG_GETSET_NAME, "/tuner1/vchannel") + h._tlv(h.TAG_GETSET_VALUE, "36.1")
    assert h._parse_tags(payload) == {h.TAG_GETSET_NAME: "/tuner1/vchannel", h.TAG_GETSET_VALUE: "36.1"}
