"""
Sample data format reference for CAD-VLM-as-a-Judge.

Each sample directory should contain:
  - parameter.json: CAD parameters (see schema below)
  - render.png: Concatenated three-view image (front + side + iso)
  - text.txt: Natural language description of the geometry

The directory name serves as the sample ID.
Positive samples go in data/positive/, negative in data/negative/.

For negative samples, parameter.json should include an extra field:
  "_perturbation": "count_error" | "symmetry_error" | "scale_error"

Example parameter.json:
{
    "objects": [
        {
            "type": "cylinder",
            "count": 4,
            "radius": 10.0,
            "height": 50.0,
            "position": [0.0, 0.0, 0.0],
            "symmetry": "rotational"
        },
        {
            "type": "box",
            "count": 2,
            "length": 30.0,
            "width": 20.0,
            "height": 15.0,
            "position": [50.0, 0.0, 0.0],
            "symmetry": "mirror"
        }
    ],
    "assembly": "grid",
    "tolerance": 0.01
}

For negative samples, the _perturbation field is added:
{
    ...same as above but with one perturbation applied...,
    "_perturbation": "count_error"
}
"""
