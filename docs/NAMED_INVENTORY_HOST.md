# Bounded readonly named inventory Host

The native23 APIs read actual named backpack stacks and Mora. They expose no upgrade,
conversion, crafting or other consumer. This Host integration has offline fixture
coverage; actual named/bound-Mora live acceptance remains false. A successful snapshot
does not verify a complete consumption Session After or cultivation target completion.

Install the project's runtime requirements into the Python environment used to launch
the runner: `python -m pip install -r requirements-runtime.txt`. The headless OpenCV
dependency is fixed to 4.11.0.86. It supplies image matching without GUI components;
see [the package documentation](https://pypi.org/project/opencv-python-headless/) and
[OpenCV template matching](https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html).
Missing image dependencies leave the new evidence unknown. Existing readers do not
depend on the new verification branch.

For a future explicitly requested readonly run:

```powershell
python scripts/workflow.py run --profile cultivation --task 培养材料 --cultivation-named-inventory --cultivation-material-scope config/local-named-scope.json
python scripts/workflow.py run --profile cultivation --task 培养材料 --cultivation-bound-mora-check
```

The local scope accepts only `executionEnabled`, `policy` and `materials`. One public
ID/name pair already in this repository's profile data is:

```json
{
  "executionEnabled": false,
  "policy": {"originalResinBudget": 0, "condensedResinBudget": 0, "maxMinutes": 3},
  "materials": [{"materialId": "104301", "materialName": "「自由」的教导"}]
}
```

The runner injects run/step/diagnostic phase. The request admits 1–8 different exact
pairs and accepts no caller balance, cost, required quantity, coordinates or binding.
Every pair is independently resolved against the actual fixed ItemV2 CSV/ONNX files,
including full-field row hash, prototype byte length, quality/type and whole-table
cross-class/name uniqueness. Unsupported namespaces/types remain blockers. In
particular an empty 113 material type does not classify a weekly-boss source.

The JS bridge obtains a separate actual native binding receipt before the snapshot.
The controlled Windows runner independently queries unique configured executable,
PID/HWND, exact decimal process-start ticks, foreground and physical capture geometry.
Native backend generation, SystemInfo lifetime UUID and assembly MVID are not OS
facts the Host can independently measure; they are bound to the audited direct
native receipt and must stay identical through every acquisition. They are never
taken from user request JSON or manufactured by copying the result binding.

The Host validates original PNG byte/BGR hashes, actual call start/return intervals,
returned physical rectangle and one file per acquisition. It rechecks the actual
six fixed template/definition assets and recomputes the world matches from the
original PNG. It recomputes selected border pixels and count source crop, HSV mask,
contours, normalization and hashes. OCR transcripts and icon/ONNX scores come from
the trusted native original transcript; the Host does not claim to rerun OCR/ONNX.
Fresh uncached CPU V6/V4 loading, six fixed OCR assets, CSV and item ONNX versions
must agree with the current trusted runtime. Partial or missing evidence yields
unknown/null, preserving the entire native observation.

An offline benchmark using a retained private original 1920×1080 PNG and the six
actual runtime templates measured 0.154 seconds for six full-frame BGR2GRAY/
CCoeffNormed searches under OpenCV 4.11.0. This was only a performance check;
world and live verification were explicitly false. No source image or account
inventory is included in public fixtures or this document.
