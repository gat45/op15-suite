"""Lit general.architecture / general.name / general.file_type dans le header GGUF."""
import struct
import sys

FTYPES = {0: "u8", 1: "i8", 2: "u16", 3: "i16", 4: "u32", 5: "i32",
          6: "f32", 7: "bool", 8: "str", 9: "arr", 10: "u64", 11: "i64", 12: "f64"}
SCALAR = {0: ("b", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("I", 4),
          5: ("i", 4), 6: ("f", 4), 7: ("b", 1), 10: ("Q", 8), 11: ("q", 8), 12: ("d", 8)}


def read_str(f):
    (n,) = struct.unpack("<Q", f.read(8))
    return f.read(n).decode("utf-8", "replace")


def read_val(f, t):
    if t == 8:
        return read_str(f)
    if t == 9:
        (it, n) = struct.unpack("<IQ", f.read(12))
        if it == 8:  # tableau de strings : itérer
            for _ in range(n):
                read_str(f)
            return f"[str x {n}]"
        fmt, size = SCALAR[it]
        f.seek(n * size, 1)  # skip du tableau
        return f"[{FTYPES.get(it, it)} x {n}]"
    fmt, size = SCALAR[t]
    (v,) = struct.unpack("<" + fmt, f.read(size))
    return v


def gguf_info(path):
    out = {"path": path}
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"GGUF":
            return {"path": path, "error": f"magic={magic!r}"}
        (ver,) = struct.unpack("<I", f.read(4))
        (ntens,) = struct.unpack("<Q", f.read(8))
        (nkv,) = struct.unpack("<Q", f.read(8))
        out["gguf_version"] = ver
        out["n_tensors"] = ntens
        for _ in range(nkv):
            key = read_str(f)
            (t,) = struct.unpack("<I", f.read(4))
            val = read_val(f, t)
            if key in ("general.architecture", "general.name", "general.file_type",
                       "general.quantization_version", "general.size_label"):
                out[key] = val
            if "general.architecture" in out and len(out) >= 6:
                break
    return out


for p in sys.argv[1:]:
    try:
        print(gguf_info(p))
    except Exception as e:
        print({"path": p, "error": f"{type(e).__name__}: {e}"})
