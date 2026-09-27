"""List the cameras plugged into this machine, by name, in OpenCV index order.

The hub's camera chip used to ask for a bare index ("Webcam 0"), which means
nothing to someone choosing between a laptop's own camera and a USB webcam.
This asks the OS for the device names instead.

The order is what makes a name usable: on Windows `core/camera.py` opens
cameras through DirectShow (`CAP_DSHOW`), whose index N is the N-th device the
DirectShow system device enumerator returns for the video-input category — so
that same enumeration, done here through plain ctypes COM, yields names whose
position *is* the index OpenCV will open. Listing does not open any camera, so
no LED flashes and nothing is held.

Stdlib-only and import-cheap: `launcher.py` imports it, and the launcher runs
without OpenCV installed. Anything that goes wrong returns an empty list, and
the chip falls back to the plain index box.
"""

from __future__ import annotations

import glob
import os
import sys


def list_cameras() -> list[dict]:
    """[{"index": int, "name": str}, ...] in OpenCV index order; [] if unknown."""
    try:
        if sys.platform == "win32":
            names = _dshow_names()
        elif sys.platform.startswith("linux"):
            return _v4l2_cameras()
        else:
            names = []
    except Exception:  # noqa: BLE001 — a listing failure must never break the hub
        return []
    return [{"index": i, "name": n} for i, n in enumerate(names)]


def resolve_index(name: str, index: int, cameras: list[dict] | None = None) -> int:
    """The index a saved camera is at *now*.

    Indices are positions, so unplugging one camera or plugging another in
    earlier can shift them; the name is what the user actually chose. Keep the
    saved index while it still holds that name, move to the one camera with
    that name if it has shifted, and otherwise (not plugged in, or two
    identical models) leave the saved index alone.
    """
    if not name:
        return index
    cams = list_cameras() if cameras is None else cameras
    if any(c["index"] == index and c["name"] == name for c in cams):
        return index
    same = [c["index"] for c in cams if c["name"] == name]
    return same[0] if len(same) == 1 else index


# ── Windows: DirectShow system device enumerator via ctypes COM ────────────

def _dshow_names() -> list[str]:
    import ctypes
    import uuid
    from ctypes import POINTER, byref, c_long, c_ulong, c_ushort, c_void_p

    class GUID(ctypes.Structure):
        _fields_ = [("d", ctypes.c_ubyte * 16)]

    def guid(s: str) -> GUID:
        return GUID.from_buffer_copy(uuid.UUID(s).bytes_le)

    class VARIANT(ctypes.Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort),
                    ("r3", c_ushort), ("val", c_void_p), ("pad", c_void_p)]

    def method(obj, index, *argtypes):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        fn = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])
        return lambda *a: fn(obj, *a)

    def release(obj):
        if obj:                                   # IUnknown::Release
            vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
            ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)

    CLSID_SystemDeviceEnum = guid("62BE5D10-60EB-11d0-BD3B-00A0C911CE86")
    IID_ICreateDevEnum = guid("29840822-5B84-11D0-BD3B-00A0C911CE86")
    CLSID_VideoInputDeviceCategory = guid("860BB310-5D01-11d0-BD3B-00A0C911CE86")
    IID_IPropertyBag = guid("55272A00-42CB-11CE-8135-00AA004BB851")
    VT_BSTR = 8

    ole32 = ctypes.windll.ole32
    oleaut32 = ctypes.windll.oleaut32
    # The hub answers on worker threads; S_OK/S_FALSE mean we own an init to
    # undo, RPC_E_CHANGED_MODE means the thread is already initialised.
    hr = ole32.CoInitializeEx(None, 0)
    owns_init = hr in (0, 1)
    names: list[str] = []
    dev_enum = c_void_p()
    enum_mon = c_void_p()
    try:
        if ole32.CoCreateInstance(byref(CLSID_SystemDeviceEnum), None, 1,
                                  byref(IID_ICreateDevEnum), byref(dev_enum)) != 0:
            return []
        # ICreateDevEnum::CreateClassEnumerator; S_FALSE = no devices at all.
        if method(dev_enum, 3, POINTER(GUID), POINTER(c_void_p), c_ulong)(
                byref(CLSID_VideoInputDeviceCategory), byref(enum_mon), 0) != 0:
            return []
        next_ = method(enum_mon, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))
        while True:
            mon, got = c_void_p(), c_ulong()
            if next_(1, byref(mon), byref(got)) != 0 or not got.value:
                break
            name = ""
            bag = c_void_p()
            try:
                # IMoniker::BindToStorage -> IPropertyBag
                if method(mon, 9, c_void_p, c_void_p, POINTER(GUID), POINTER(c_void_p))(
                        None, None, byref(IID_IPropertyBag), byref(bag)) == 0:
                    var = VARIANT()
                    if method(bag, 3, ctypes.c_wchar_p, POINTER(VARIANT), c_void_p)(
                            "FriendlyName", byref(var), None) == 0:
                        if var.vt == VT_BSTR and var.val:
                            name = ctypes.wstring_at(var.val)
                        oleaut32.VariantClear(byref(var))
            finally:
                release(bag)
                release(mon)
            # Every enumerated device takes an index, named or not.
            names.append(name.strip() or f"Camera {len(names)}")
    finally:
        release(enum_mon)
        release(dev_enum)
        if owns_init:
            ole32.CoUninitialize()
    return names


# ── Linux: V4L2 names from sysfs ───────────────────────────────────────────

def _v4l2_cameras() -> list[dict]:
    cams = []
    for path in glob.glob("/sys/class/video4linux/video*"):
        try:
            idx = int(os.path.basename(path)[5:])
            # Each UVC camera also exposes a metadata node; only the capture
            # node (sysfs "index" 0) is one OpenCV can open.
            with open(os.path.join(path, "index"), encoding="utf-8") as fh:
                if fh.read().strip() != "0":
                    continue
            with open(os.path.join(path, "name"), encoding="utf-8") as fh:
                cams.append({"index": idx, "name": fh.read().strip() or f"Camera {idx}"})
        except (OSError, ValueError):
            continue
    return sorted(cams, key=lambda c: c["index"])


if __name__ == "__main__":
    for cam in list_cameras():
        print(f"{cam['index']}: {cam['name']}")
