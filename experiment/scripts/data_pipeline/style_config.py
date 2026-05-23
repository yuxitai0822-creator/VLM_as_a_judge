"""
Global style configuration for benchmark rendering.

Positive and negative samples MUST share identical style.
Only geometry perturbation differs between them.
"""

# ── Image ───────────────────────────────────────────────────────────────
COLLAGE_SIZE = 1475
VIEW_DPI = 150

# ── Layout (matching original TriView2CAD DXF) ─────────────────────────
GAP_V = 500
GAP_H = 350

# ── Dimension band hierarchy ───────────────────────────────────────────
# Bands define how far each tier of dimensions sits from geometry.
# BAND1 = local feature dims, BAND2 = spacing, BAND3 = overall.
BAND1_OFFSET = 45       # first tier from geometry edge
BAND2_OFFSET = 80       # second tier
BAND3_OFFSET = 115      # third tier (overall)

# ── Annotation line styling ────────────────────────────────────────────
GEOMETRY_LINE_WIDTH = 2
ANNOTATION_LINE_WIDTH = 1
EXTENSION_LINE_WIDTH = 1
ARROW_LENGTH = 15       # long and thin (CAD style)
ARROW_WIDTH = 2.5       # narrow
EXTENSION_OVERSHOOT = 10  # extension line past dim line
EXTENSION_OFFSET = 3    # gap between geometry edge and extension line start

# ── Text (CAD-style font) ──────────────────────────────────────────────
FONT_SIZE = 14
FONT_NAME = "consola.ttf"   # Consolas — monospaced, technical feel
TEXT_COLOR = (0, 0, 0)
TEXT_BG_PADDING = 2
TEXT_BG_COLOR = (255, 255, 255)

# ── Colors ──────────────────────────────────────────────────────────────
BG_COLOR = (255, 255, 255)
LINE_COLOR = (0, 0, 0)
