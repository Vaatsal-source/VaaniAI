"""Fill {{snip_name}} markers in README.template.md with the generated tables -> README.md"""
import pathlib, re
R = pathlib.Path(__file__).resolve().parent.parent
t = (R / "README.template.md").read_text(encoding="utf-8")
t = re.sub(r"\{\{(snip_\w+)\}\}", lambda m: (R / "results" / f"{m.group(1)}.md").read_text(encoding="utf-8").strip(), t)
(R / "README.md").write_text(t, encoding="utf-8"); print("README.md written", len(t), "chars")
