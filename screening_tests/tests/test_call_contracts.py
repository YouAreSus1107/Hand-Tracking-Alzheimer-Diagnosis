"""
Static call-contract check for the test entry scripts -- no camera, no window.

The run loops only reach some of their calls in particular live states (a hand
at the edge, a finished run, a lost camera), so a call that no longer matches
the function it calls can sit there unnoticed until a patient trips it. That
is how the tremor test crashed: it handed the shared edge-warning helper its
own Toasts object where a Coach belongs, plus an extra positional argument,
and only a clipped hand ever reached that line.

This walks every call in each entry script and checks it against the real
function, using the script's own imported names:

  * the arguments bind to the signature (count, names, keyword-only);
  * where a parameter is annotated with a class and the argument's class is
    known -- `self.x` built in the class as `self.x = SomeClass(...)`, a local
    built as `c = Canvas(...)`, or a parameter annotated `c: Canvas` -- the
    argument is an instance of it;
  * a method called on such an attribute or local exists on its class.

Only functions defined in this repo are checked (cv2 and friends have no
introspectable signatures). Anything it cannot resolve it skips rather than
guesses, so a failure here is always a real mismatch.

Run:  python screening_tests/tests/test_call_contracts.py
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import typing
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core"))

SCRIPTS = sorted((_REPO_ROOT / "screening_tests").glob("*.py")) + [
    _REPO_ROOT / "core" / "hand_tracking.py",
    _REPO_ROOT / "core" / "mirror_check.py",
]

_MISSING = object()


def _load(path: Path):
    """Import an entry script as a module (not __main__, so main() and the
    console splash never run)."""
    name = f"_contract_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ATTRS: dict[type, set[str]] = {}


def _instance_attrs(cls: type) -> set[str]:
    """Every `self.x` a class (or a base of ours) assigns anywhere, from its
    source. Anything we cannot read makes the answer "all of them", so an
    unreadable class never produces a false 'no attribute' failure."""
    if cls in _ATTRS:
        return _ATTRS[cls]
    names: set[str] = set(getattr(cls, "__annotations__", {}))
    for k in cls.__mro__:
        if k is object:
            continue
        if not _ours(k):
            names = _AnyName()
            break
        try:
            tree = ast.parse(inspect.getsource(k).lstrip()
                             if k.__module__ != "_contract_probe"
                             else "pass")
        except (OSError, TypeError, SyntaxError, IndentationError):
            names = _AnyName()
            break
        for sub in ast.walk(tree):
            tgt_list = []
            if isinstance(sub, ast.Assign):
                tgt_list = sub.targets
            elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
                tgt_list = [sub.target]
            for tgt in tgt_list:
                for t in ast.walk(tgt):
                    if (isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"):
                        names.add(t.attr)
        names |= set(getattr(k, "__slots__", ()) or ())
    _ATTRS[cls] = names
    return names


class _AnyName(set):
    def __contains__(self, item):
        return True


def _ours(obj) -> bool:
    mod = getattr(obj, "__module__", "") or ""
    return mod.startswith(("core", "_contract_", "screening_tests"))


class _Checker(ast.NodeVisitor):
    def __init__(self, mod, path: Path):
        self.mod = mod
        self.path = path
        self.errors: list[str] = []
        self.cls: type | None = None
        self.self_types: dict[type, dict[str, type]] = {}
        self.local_types: dict[str, type] = {}

    # ── resolution ────────────────────────────────────────────────────────
    def resolve(self, node):
        """The object an expression names, or _MISSING. `self.x` resolves to
        the class of x (or the bound attribute on our own class)."""
        if isinstance(node, ast.Name):
            if node.id == "self" and self.cls is not None:
                return ("instance", self.cls)
            if node.id in self.local_types:
                return ("instance", self.local_types[node.id])
            return self.mod.__dict__.get(node.id, _MISSING)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            if base is _MISSING:
                return _MISSING
            if isinstance(base, tuple):
                if base[0] != "instance":
                    return _MISSING                     # attribute of a method etc.
                cls = base[1]
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    attr_t = self.self_types.get(cls, {}).get(node.attr)
                    if attr_t is not None:
                        return ("instance", attr_t)
                val = inspect.getattr_static(cls, node.attr, _MISSING)
                if val is _MISSING:
                    if (node.attr in _instance_attrs(cls)
                            or hasattr(cls, "__getattr__")):
                        return _MISSING                 # set in a method; type unknown
                    return ("unknown-attr", cls, node.attr)
                if isinstance(val, (staticmethod, classmethod)) or inspect.isfunction(val):
                    return ("method", cls, val)
                return _MISSING                         # property / class data
            return getattr(base, node.attr, _MISSING)
        return _MISSING

    def class_of(self, node) -> type | None:
        """The class an argument expression is an instance of, when known."""
        r = self.resolve(node)
        if isinstance(r, tuple) and r[0] == "instance":
            return r[1]
        if isinstance(node, ast.Call):
            f = self.resolve(node.func)
            if isinstance(f, type):
                return f
        return None

    def ctor(self, value) -> type | None:
        if isinstance(value, ast.Call):
            f = self.resolve(value.func)
            if isinstance(f, type):
                return f
        return None

    # ── scopes ────────────────────────────────────────────────────────────
    def visit_ClassDef(self, node):
        cls = self.mod.__dict__.get(node.name)
        if not isinstance(cls, type):
            return
        prev, self.cls = self.cls, cls
        # First pass: what each self.x is built as. An attribute assigned two
        # different classes is left unknown rather than guessed.
        types: dict[str, type | None] = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    if (isinstance(tgt, ast.Attribute)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"):
                        t = self.ctor(sub.value)
                        if t is None:
                            continue
                        if types.get(tgt.attr, t) is not t:
                            types[tgt.attr] = None
                        else:
                            types[tgt.attr] = t
        self.self_types[cls] = {k: v for k, v in types.items() if v is not None}
        self.generic_visit(node)
        self.cls = prev

    def visit_FunctionDef(self, node):
        prev = self.local_types
        self.local_types = {}
        fn = None
        if self.cls is not None:
            fn = inspect.getattr_static(self.cls, node.name, None)
        elif node.name in self.mod.__dict__:
            fn = self.mod.__dict__[node.name]
        hints = {}
        if callable(fn):
            try:
                hints = typing.get_type_hints(fn)
            except Exception:  # noqa: BLE001 - an unresolvable hint is skipped
                hints = {}
        for a in node.args.args + node.args.kwonlyargs:
            h = hints.get(a.arg)
            if isinstance(h, type) and _ours(h):
                self.local_types[a.arg] = h
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Assign) and len(sub.targets) == 1
                    and isinstance(sub.targets[0], ast.Name)):
                t = self.ctor(sub.value)
                if t is not None and _ours(t):
                    self.local_types[sub.targets[0].id] = t
        self.generic_visit(node)
        self.local_types = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    # ── calls ─────────────────────────────────────────────────────────────
    def visit_Call(self, node):
        self.generic_visit(node)
        if any(isinstance(a, ast.Starred) for a in node.args) or \
                any(k.arg is None for k in node.keywords):
            return                                        # *args / **kw: unknowable
        target = self.resolve(node.func)
        where = f"{self.path.name}:{node.lineno}"
        bound_self = False
        if isinstance(target, tuple):
            if target[0] == "unknown-attr":
                self.errors.append(f"{where}: {target[1].__name__} has no "
                                   f"attribute '{target[2]}'")
                return
            if target[0] != "method":
                return
            val = target[2]
            if isinstance(val, staticmethod):
                fn = val.__func__
            elif isinstance(val, classmethod):
                fn, bound_self = val.__func__, True
            elif inspect.isfunction(val):
                fn, bound_self = val, True
            else:
                return                                    # property, data, etc.
        else:
            fn = target
        if fn is _MISSING or not callable(fn) or not _ours(fn):
            return
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return
        args = list(node.args)
        placeholders = ([object()] if bound_self else []) + args
        kwargs = {k.arg: k.value for k in node.keywords}
        try:
            ba = sig.bind(*placeholders, **kwargs)
        except TypeError as e:
            name = getattr(fn, "__qualname__", repr(fn))
            self.errors.append(f"{where}: {name}{sig} -- {e}")
            return
        try:
            hints = typing.get_type_hints(fn.__init__ if isinstance(fn, type) else fn)
        except Exception:  # noqa: BLE001
            return
        for pname, val in ba.arguments.items():
            want = hints.get(pname)
            if not (isinstance(want, type) and _ours(want)):
                continue
            if not isinstance(val, ast.AST):
                continue
            got = self.class_of(val)
            if got is not None and not issubclass(got, want):
                name = getattr(fn, "__qualname__", repr(fn))
                self.errors.append(
                    f"{where}: {name}() parameter '{pname}' wants "
                    f"{want.__name__}, gets {got.__name__}")


def _check(path: Path) -> list[str]:
    mod = _load(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    chk = _Checker(mod, path)
    chk.visit(tree)
    return chk.errors


def _make_test(path: Path):
    def test():
        errors = _check(path)
        assert not errors, "\n    " + "\n    ".join(errors)
    test.__name__ = f"test_calls_match_signatures_{path.stem}"
    return test


for _p in SCRIPTS:
    globals()[f"test_calls_match_signatures_{_p.stem}"] = _make_test(_p)


def test_checker_catches_the_tremor_bug():
    """The exact mistake that crashed the tremor test must be caught."""
    src = '''
from core.ui.framing_ui import draw_framing
class Toasts:
    def show(self, msg): pass
class App:
    def __init__(self):
        self.toasts = Toasts()
    def run(self, c, mon, pts, now):
        draw_framing(c, mon, pts, self.toasts, now)
'''
    import types as _t
    mod = _t.ModuleType("_contract_probe")
    exec(compile(src, "probe.py", "exec"), mod.__dict__)
    for obj in (mod.Toasts, mod.App):
        obj.__module__ = "_contract_probe"
    chk = _Checker(mod, Path("probe.py"))
    chk.visit(ast.parse(src))
    joined = "\n".join(chk.errors)
    assert "positional" in joined, joined            # the stray `now`
    src2 = src.replace(", now)", ")")
    chk = _Checker(mod, Path("probe.py"))
    chk.visit(ast.parse(src2))
    assert any("wants Coach, gets Toasts" in e for e in chk.errors), chk.errors


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 - a script that will not import
            failed += 1
            print(f"  FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
