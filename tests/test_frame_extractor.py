from stackant.frame_extractor import build_ffmpeg_args


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
