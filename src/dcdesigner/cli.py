"""Command line: dcd compile | report | config | web."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import nos
from .catalog import load_catalog
from .compiler import canonical_json, compile_design
from .fabric import plan_fabric
from .report import markdown
from .schema import DesignSpec
from .wiring import Wiring

ROOT = Path(__file__).resolve().parents[2]


def load_spec(path: str | Path) -> DesignSpec:
    return DesignSpec.model_validate(yaml.safe_load(Path(path).read_text()))


def _catalog(args):
    return load_catalog(args.catalog, args.references)


def cmd_compile(args) -> int:
    doc = compile_design(load_spec(args.spec), _catalog(args))
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_report(args) -> int:
    doc = compile_design(load_spec(args.spec), _catalog(args))
    text = markdown(doc)
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_config(args) -> int:
    spec = load_spec(args.spec)
    cat = _catalog(args)
    doc = compile_design(spec, cat)
    wiring = Wiring(spec, plan_fabric(spec, cat))
    dev = wiring.device(args.role, args.plane, args.index)
    sys.stdout.write(nos.render(args.nos, dev, doc["roce"]))
    return 0


def build_web(presets: list[Path], out_dir: Path, cat) -> list[str]:
    """Writes web/designs.js (window.DESIGNS) so the viewer works from file:// with no server."""
    docs = {}
    for p in sorted(presets):
        spec = load_spec(p)
        doc = compile_design(spec, cat)
        wiring = Wiring(spec, plan_fabric(spec, cat))
        samples = {}
        for role in ("leaf", "spine", "super"):
            try:
                dev = wiring.device(role, 0, 0)
            except Exception:
                continue
            samples[role] = {n: nos.render(n, dev, doc["roce"]) for n in spec.nos}
            samples[role]["_name"] = dev.name
        doc["sample_configs"] = samples
        docs[doc["name"]] = doc
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "designs.js").write_text("window.DESIGNS = " + canonical_json(docs) + ";\n")
    return list(docs)


def cmd_web(args) -> int:
    presets = [Path(p) for p in args.presets] or sorted((ROOT / "presets").glob("*.yaml"))
    names = build_web(presets, Path(args.out), _catalog(args))
    print(f"wrote {Path(args.out) / 'designs.js'} with {', '.join(names)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dcd", description="Silicon-to-Data-Hall deterministic AI data center compiler")
    ap.add_argument("--catalog", type=Path, help="override the component catalog YAML")
    ap.add_argument("--references", type=Path, help="override the references YAML")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="compile a design spec to the full design JSON")
    p.add_argument("spec")
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_compile)

    p = sub.add_parser("report", help="markdown report with a BOM summary per tier")
    p.add_argument("spec")
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("config", help="render one switch's NOS config")
    p.add_argument("spec")
    p.add_argument("--nos", choices=["sonic", "eos", "nxos"], default="sonic")
    p.add_argument("--role", choices=["leaf", "spine", "super"], default="leaf")
    p.add_argument("--plane", type=int, default=0)
    p.add_argument("--index", type=int, default=0)
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("web", help="compile presets into the static web viewer's data file")
    p.add_argument("presets", nargs="*")
    p.add_argument("--out", default=str(ROOT / "web"))
    p.set_defaults(fn=cmd_web)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
