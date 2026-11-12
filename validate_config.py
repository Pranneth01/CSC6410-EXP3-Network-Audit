"""Class 2 demo: build a switch configuration as data and validate it before it goes anywhere (CSC 6410, Week 3).
   pip install jsonschema        python validate_config.py
   Files: switch_schema.json (JSON Schema written from campus-switch.yang)."""
import copy, json, pathlib
from jsonschema import Draft202012Validator

HERE = pathlib.Path(__file__).parent
SCHEMA = json.loads((HERE / "switch_schema.json").read_text())
TOP = "campus-switch:switch"            # RFC 7951: top-level member = "module-name:node"

# 1. The intended configuration, built in Python (a dict = a JSON object, a list = a JSON array)
good = {TOP: {
    "hostname": "sci-sw1",
    "vlan": [{"id": 10, "name": "staff"},
             {"id": 20, "name": "students"},
             {"id": 30, "name": "cameras", "enabled": False}],
    "interface": [{"name": "ge-0/0/1", "description": "Room 114 wall jack", "access-vlan": 20},
                  {"name": "ge-0/0/48", "description": "Uplink to core", "mtu": 9000}]}}


def broken(change):
    """Copy the good config and apply one mistake to it."""
    c = copy.deepcopy(good)
    change(c[TOP])
    return c


CASES = {
    "good": good,
    "a: VLAN 4095": broken(lambda s: s["vlan"].append({"id": 4095, "name": "test"})),
    "b: id as text": broken(lambda s: s["vlan"][1].update(id="20")),
    "c: no name": broken(lambda s: s["vlan"].append({"id": 40})),
    "d: VLAN 40 on a port": broken(lambda s: s["interface"][0].update({"access-vlan": 40})),
    "e: VLAN 10 twice": broken(lambda s: s["vlan"].append({"id": 10, "name": "staff-2"})),
}


def schema_errors(cfg):
    """Step 1: types, ranges, required leaves - everything JSON Schema can express."""
    v = Draft202012Validator(SCHEMA)
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in v.iter_errors(cfg)]


def model_errors(cfg):
    """Step 2: rules JSON Schema cannot express - YANG list keys must be unique; a leafref must point at a real VLAN."""
    s, errs = cfg[TOP], []
    ids = [v["id"] for v in s.get("vlan", []) if isinstance(v.get("id"), int)]
    errs += [f"vlan {i}: key used twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for p in s.get("interface", []):
        if "access-vlan" in p and p["access-vlan"] not in ids:
            errs.append(f"interface {p['name']}: access-vlan {p['access-vlan']} does not exist (leafref)")
    return errs


if __name__ == "__main__":
    print("JSON for the good config:", len(json.dumps(good, separators=(",", ":"))), "bytes (compact)")
    for name, cfg in CASES.items():
        e1, e2 = schema_errors(cfg), model_errors(cfg)
        verdict = "VALID" if not (e1 or e2) else "REJECT"
        print(f"{name:<22} {verdict}")
        for e in e1:
            print(f"    schema: {e}")
        for e in e2:
            print(f"    model:  {e}")
