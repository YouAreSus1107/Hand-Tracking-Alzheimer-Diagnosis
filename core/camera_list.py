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
    return enumerate_cameras()[0]


def enumerate_cameras() -> tuple[list[dict], bool]:
    """(cameras, listed). `listed` is False when the OS could not be asked,
    which the chip must not read as "nothing is plugged in".

    On Windows each entry also carries `virtual`: True when DirectShow lists
    the device but Media Foundation does not. That is almost always a virtual
    camera (OBS, Snap, some vendor "effects" filters), and it matters beyond
    the label: OpenCV's MSMF backend numbers cameras by Media Foundation's
    list, so every DirectShow-only entry shifts the MSMF index of the cameras
    after it (see msmf_index()).
    """
    try:
        if sys.platform == "win32":
            names = _dshow_names()
        elif sys.platform.startswith("linux"):
            return _v4l2_cameras(), True
        else:
            return [], False
    except Exception:  # noqa: BLE001 — a listing failure must never break the hub
        return [], False
    cams = [{"index": i, "name": n} for i, n in enumerate(names)]
    mf = msmf_names()
    if mf is not None:
        for cam in cams:
            cam["virtual"] = cam["name"] not in mf
    return cams, True


def msmf_names() -> list[str] | None:
    """Media Foundation's video-capture devices in the order OpenCV's MSMF
    backend indexes them; None when they cannot be listed (not Windows, or
    the enumeration failed) — distinct from [] (listed, none present)."""
    if sys.platform != "win32":
        return None
    try:
        return _mf_names()
    except Exception:  # noqa: BLE001
        return None


def msmf_index(name: str, dshow_index: int,
               dshow: list[str] | None = None,
               mf: list[str] | None = None) -> int | None:
    """The index to hand cv2.CAP_MSMF for the camera DirectShow calls
    `dshow_index` (named `name`).

    The two backends number cameras independently, so the same integer can
    open a *different* camera under MSMF — which is exactly the fallback
    core/camera.open_capture() takes for the cameras that only reach 60 fps
    there. Matched by name; among several identical models, by their order
    within that name, which both enumerators keep in device-arrival order.

    Returns None when Media Foundation does not list the camera at all (a
    DirectShow-only virtual camera: MSMF cannot open it, and trying its
    index would open something else), and `dshow_index` unchanged when
    either list is unavailable, so nothing is worse than before.
    """
    if not name:
        return dshow_index
    mf = msmf_names() if mf is None else mf
    if mf is None:
        return dshow_index
    same_mf = [i for i, n in enumerate(mf) if n == name]
    if not same_mf:
        return None
    if len(same_mf) == 1:
        return same_mf[0]
    if dshow is None:
        try:
            dshow = _dshow_names() if sys.platform == "win32" else None
        except Exception:  # noqa: BLE001
            dshow = None
    if dshow is None:
        return dshow_index
    same_ds = [i for i, n in enumerate(dshow) if n == name]
    if dshow_index in same_ds and same_ds.index(dshow_index) < len(same_mf):
        return same_mf[same_ds.index(dshow_index)]
    return dshow_index


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


# ── Windows: Media Foundation device sources via ctypes COM ────────────────
# The list cv2.CAP_MSMF indexes into: MFEnumDeviceSources filtered to video
# capture, in the order it returns them. Enumerating activates nothing.

def _mf_names() -> list[str]:
    import ctypes
    import uuid
    from ctypes import POINTER, byref, c_long, c_uint32, c_ulong, c_void_p, c_wchar_p

    class GUID(ctypes.Structure):
        _fields_ = [("d", ctypes.c_ubyte * 16)]

    def guid(s: str) -> GUID:
        return GUID.from_buffer_copy(uuid.UUID(s).bytes_le)

    def method(obj, index, *argtypes):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        fn = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])
        return lambda *a: fn(obj, *a)

    def release(obj):
        if obj:
            vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
            ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)

    SOURCE_TYPE = guid("c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3")
    SOURCE_TYPE_VIDCAP = guid("8ac3587a-4ae7-42d8-99e0-0a6013eef90f")
    FRIENDLY_NAME = guid("60d0e559-52f8-4fa2-bbce-acdb34a8ec01")
    MF_VERSION = 0x00020070
    MFSTARTUP_LITE = 1

    ole32 = ctypes.windll.ole32
    mfplat = ctypes.windll.mfplat
    mf = ctypes.windll.mf
    ole32.CoTaskMemFree.argtypes = [c_void_p]
    hr = ole32.CoInitializeEx(None, 0)
    owns_init = hr in (0, 1)
    if mfplat.MFStartup(MF_VERSION, MFSTARTUP_LITE) != 0:
        if owns_init:
            ole32.CoUninitialize()
        raise OSError("MFStartup failed")
    names: list[str] = []
    attrs = c_void_p()
    devices = POINTER(c_void_p)()
    count = c_uint32()
    try:
        if mfplat.MFCreateAttributes(byref(attrs), 1) != 0:
            raise OSError("MFCreateAttributes failed")
        # IMFAttributes::SetGUID (vtable slot 24)
        if method(attrs, 24, POINTER(GUID), POINTER(GUID))(
                byref(SOURCE_TYPE), byref(SOURCE_TYPE_VIDCAP)) != 0:
            raise OSError("SetGUID failed")
        if mf.MFEnumDeviceSources(attrs, byref(devices), byref(count)) != 0:
            raise OSError("MFEnumDeviceSources failed")
        try:
            for i in range(count.value):
                act = c_void_p(devices[i])
                text, length = c_wchar_p(), c_uint32()
                try:
                    # IMFAttributes::GetAllocatedString (slot 13); IMFActivate
                    # inherits IMFAttributes, so the slot is the same.
                    if method(act, 13, POINTER(GUID), POINTER(c_wchar_p), POINTER(c_uint32))(
                            byref(FRIENDLY_NAME), byref(text), byref(length)) == 0:
                        name = text.value or ""
                        ole32.CoTaskMemFree(ctypes.cast(text, c_void_p))
                    else:
                        name = ""
                finally:
                    release(act)
                names.append(name.strip() or f"Camera {i}")
        finally:
            if devices:
                ole32.CoTaskMemFree(ctypes.cast(devices, c_void_p))
    finally:
        release(attrs)
        mfplat.MFShutdown()
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
    cams, listed = enumerate_cameras()
    if not listed:
        print("Cameras could not be listed on this machine.")
    for cam in cams:
        tag = "  (DirectShow only)" if cam.get("virtual") else ""
        print(f"{cam['index']}: {cam['name']}{tag}")
    mf = msmf_names()
    if mf is not None:
        print("Media Foundation order:")
        for i, name in enumerate(mf):
            print(f"{i}: {name}")
