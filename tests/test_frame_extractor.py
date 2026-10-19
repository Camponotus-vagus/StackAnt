from pathlib import Path

from stackant.frame_extractor import (
    build_ffmpeg_args,
    build_ffprobe_args,
    frame_sort_key,
    parse_frame_count,
)


def test_basic_args_include_input_and_output_pattern():
    args = build_ffmpeg_args("/tmp/in.mp4", "/tmp/out", decimation=1)
    assert "/tmp/in.mp4" in args
    # output pattern ends up as last element
    assert args[-1].endswith("frame_%05d.tif")
    assert "-fps_mode" in args
    assert "vfr" in args


def test_no_select_filter_when_decimation_is_one():
    args = build_ffmpeg_args("/tmp/in.mp4", "/tmp/out", decimation=1)
    assert "-vf" not in args


def test_select_filter_present_for_decimation_gt_one():
    args = build_ffmpeg_args("/tmp/in.mp4", "/tmp/out", decimation=5)
    assert "-vf" in args
    idx = args.index("-vf")
    assert "mod(n" in args[idx + 1]
    assert "5" in args[idx + 1]


def test_start_and_end_seconds_emit_ss_and_to():
    args = build_ffmpeg_args(
        "/tmp/in.mp4", "/tmp/out", decimation=1, start_sec=1.5, end_sec=4.0
    )
    assert "-ss" in args
    assert "-to" in args
    # -ss comes before -i
    assert args.index("-ss") < args.index("-i")


def test_output_pattern_is_relative_so_percent_in_dir_is_harmless():
    args = build_ffmpeg_args("/tmp/in.mp4", "/tmp/100%/out", decimation=1)
    assert args[-1] == "frame_%05d.tif"


def test_ffprobe_args_read_headers_only_and_guard_dash_names():
    args = build_ffprobe_args("-weird.mp4")
    assert "-count_packets" not in args
    assert args[-2:] == ["-i", "-weird.mp4"]


def test_parse_frame_count_prefers_nb_frames():
    js = '{"streams":[{"nb_frames":"240","duration":"9","avg_frame_rate":"30/1"}]}'
    assert parse_frame_count(js) == 240


def test_parse_frame_count_falls_back_to_duration_times_rate():
    js = '{"streams":[{"nb_frames":"N/A","avg_frame_rate":"30000/1001"}],"format":{"duration":"10.0"}}'
    assert parse_frame_count(js) == 300


def test_parse_frame_count_garbage_is_none():
    assert parse_frame_count("") is None
    assert parse_frame_count("not json") is None
    assert parse_frame_count('{"streams":[]}') is None
    assert parse_frame_count('{"streams":[{"avg_frame_rate":"0/0"}]}') is None


def test_frame_sort_key_is_numeric_past_five_digits():
    names = ["frame_99999.tif", "frame_100000.tif", "frame_00002.tif"]
    ordered = sorted((Path(n) for n in names), key=frame_sort_key)
    assert [p.name for p in ordered] == [
        "frame_00002.tif", "frame_99999.tif", "frame_100000.tif",
    ]
