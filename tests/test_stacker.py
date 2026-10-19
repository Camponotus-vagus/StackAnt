from stackant.stacker import (
    build_focus_stack_args,
    is_opencl_failure,
    should_retry_without_opencl,
    split_common_directory,
)


def test_basic_args_contain_defaults_and_frames():
    args = build_focus_stack_args(["/tmp/a.tif", "/tmp/b.tif"], "/tmp/out.tif")
    assert "--output=/tmp/out.tif" in args
    assert "--consistency=2" in args
    assert "--denoise=1" in args
    # --sharp-strength is no longer emitted: the installed focus-stack has no
    # such option and warns on unknown flags.
    assert not any(a.startswith("--sharp-strength") for a in args)
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


# focus-stack's OpenCL wavelet kernel fails on macOS' deprecated OpenCL stack.
# The real failure log (frame 188 of the user's run) ends with many repeated
# progress lines, so the OpenCL signature can scroll past the last 800 bytes —
# detection must scan the full captured log, not just the tail.

def test_is_opencl_failure_detects_kernel_error():
    assert is_opencl_failure("Task ...\nFailed to execute OpenCL kernel\n")
    assert is_opencl_failure("can't create cl_mem handle for passed UMat buffer")
    assert is_opencl_failure("clEnqueue... CL_OUT_OF_RESOURCES")
    assert is_opencl_failure("OPENCL: kernel set failed")  # case-insensitive


def test_is_opencl_failure_false_for_unrelated_errors():
    assert not is_opencl_failure("focus-stack exited with code 1:\nFile not found")
    assert not is_opencl_failure("")


def test_should_retry_without_opencl_happy_path():
    assert should_retry_without_opencl(
        "Failed to execute OpenCL kernel",
        compare_mode=False,
        already_retried=False,
        extra_cli="",
    )


def test_should_retry_blocked_by_each_guard():
    msg = "Failed to execute OpenCL kernel"
    # not an OpenCL failure
    assert not should_retry_without_opencl(
        "generic error", compare_mode=False, already_retried=False, extra_cli=""
    )
    # compare mode runs both backends; never auto-retry there
    assert not should_retry_without_opencl(
        msg, compare_mode=True, already_retried=False, extra_cli=""
    )
    # already retried once — don't loop
    assert not should_retry_without_opencl(
        msg, compare_mode=False, already_retried=True, extra_cli=""
    )
    # OpenCL was already disabled, so a retry would change nothing
    assert not should_retry_without_opencl(
        msg, compare_mode=False, already_retried=False, extra_cli="--no-opencl"
    )


def test_opencl_banner_mentioning_opencl_is_not_a_failure():
    assert not is_opencl_failure("OpenCL device: Intel(R) UHD Graphics\nUsing OpenCL")
    assert is_opencl_failure("OpenCL error -5 in kernel")
    assert is_opencl_failure("CL_INVALID_KERNEL_ARGS")


def test_extra_cli_unbalanced_quote_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        build_focus_stack_args(["a.tif"], "o.tif", extra_cli='--x="oops')


def test_extra_cli_keeps_windows_backslashes_in_nt_mode(monkeypatch):
    import stackant.stacker as st
    monkeypatch.setattr(st.os, "name", "nt")
    args = build_focus_stack_args(["a.tif"], "o.tif", extra_cli=r"--tmp=C:\Users\me\t")
    assert r"--tmp=C:\Users\me\t" in args


def test_split_common_directory_uses_bare_names(tmp_path):
    frames = [str(tmp_path / f"f{i}.tif") for i in range(3)]
    workdir, names = split_common_directory(frames)
    assert workdir == str(tmp_path)
    assert names == ["f0.tif", "f1.tif", "f2.tif"]


def test_split_common_directory_mixed_dirs_unchanged(tmp_path):
    frames = [str(tmp_path / "a.tif"), str(tmp_path / "sub" / "b.tif")]
    assert split_common_directory(frames) == (None, frames)


def test_split_common_directory_protects_dash_names(tmp_path):
    _, names = split_common_directory([str(tmp_path / "-a.tif")])
    assert names == ["./-a.tif"]


def test_opencl_device_info_lines_are_not_failures():
    from stackant.stacker import is_opencl_failure
    assert not is_opencl_failure("Device type: CL_DEVICE_TYPE_GPU\nCL_PLATFORM_NAME: Apple")
    assert is_opencl_failure("clEnqueueNDRangeKernel returned CL_OUT_OF_RESOURCES")
    assert is_opencl_failure("error: CL_INVALID_COMMAND_QUEUE")
    assert is_opencl_failure("CL_MEM_OBJECT_ALLOCATION_FAILURE")
