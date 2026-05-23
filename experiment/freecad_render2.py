import sys, os
sys.path.insert(0, r"C:\Program Files\FreeCAD 1.1\bin")
sys.path.insert(0, r"C:\Program Files\FreeCAD 1.1\lib")

import FreeCAD
import Import

dxf_path = r"D:\PythonProgramming\CAD Generation\VLM_as_a_judge\experiment\data\negative\sample_001_count_error\temp.dxf"
out_path = r"D:\PythonProgramming\CAD Generation\VLM_as_a_judge\experiment\_freecad_test.png"

doc = FreeCAD.newDocument("render")
Import.readDXF(dxf_path, doc.Name)
doc.recompute()
print(f"Objects: {len(doc.Objects)}")

from FreeCAD import Gui
view = Gui.ActiveDocument.ActiveView
view.viewIsometric()
view.fitAll()
view.saveImage(out_path, 2950, 2950, "Current")
print(f"Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
FreeCAD.closeDocument("render")
