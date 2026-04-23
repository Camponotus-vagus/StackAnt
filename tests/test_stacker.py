from stackant.stacker import build_focus_stack_args


def test_basic_args_contain_defaults_and_frames():
    args = build_focus_stack_args(["/tmp/a.tif", "/tmp/b.tif"], "/tmp/out.tif")
    assert "--output=/tmp/out.tif" in args
    assert "--consistency=2" in args
    assert "--denoise=1" in args
    assert "--sharp-strength=1" in args
    # frame paths appear at the tail
    assert args[-2:] == ["/tmp/a.tif", "/tmp/b.tif"]


def test_denoise_off_emits_zero():
    args = build_focus_stack_args(["/tmp/a.tif"], "/tmp/out.tif", denoise=False)
    assert "--denoise=0" in args


def test_halo_radius_only_included_when_provided():
    default = build_focus_stack_args(["/tmp/a.tif"], "/tmp/out.tif")
    assert not any(a.startswith("--halo-radius") for a in default)
    with_halo = build_focus_stack_args(
        ["/tmp/a.tif"], "/tmp/out.tif", halo_radius=5
    )
    assert "--halo-radius=5" in with_halo


def test_extra_cli_is_split_and_appended_before_frames():
    args = build_focus_stack_args(
        ["/tmp/a.tif"], "/tmp/out.tif", extra_cli="--verbose --threads=4"
    )
    assert "--verbose" in args
    assert "--threads=4" in args
    # the frame file must still be last
    assert args[-1] == "/tmp/a.tif"


def test_consistency_int_cast():
    args = build_focus_stack_args(["/tmp/a.tif"], "/tmp/o.tif", consistency=3)
    assert "--consistency=3" in args
