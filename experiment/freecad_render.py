import FreeCAD, Import, os, sys

dxf_path = r"D:\PythonProgramming\CAD Generation\VLM_as_a_judge\experiment\data\negative\sample_001_count_error\temp.dxf"
out_path = r"D:\PythonProgramming\CAD Generation\VLM_as_a_judge\experiment\_freecad_test.png"

doc = FreeCAD.newDocument("render")
Import.readDXF(dxf_path, doc.Name)
doc.recompute()

from FreeCAD import Gui
view = Gui.ActiveDocument.ActiveView
view.viewIsometric()
view.fitAll()
view.saveImage(out_path, 2950, 2950, "Current")

FreeCAD.closeDocument("render")

# Force quit FreeCAD
from PySide2 import QtWidgets
app = QtWidgets.QApplication.instance()
app.quit()
