GROUP_NAME = "Sign Panel"
CATEGORY = "Decorative"
DESCRIPTION = "Backlit signboard in the local XZ plane facing -Y: glowing panel with a dark bezel and raised glyph strokes set from a text string, running vertically or horizontally."


def build(b, context):
    text = b.input("Text", "STRING", "RAIN")
    width = b.input("Width", "FLOAT", 1.2, 0.05, 50.0, "DISTANCE")
    height = b.input("Height", "FLOAT", 3.0, 0.05, 50.0, "DISTANCE")
    vertical = b.input("Vertical", "BOOL", True)
    bezel = b.input("Bezel", "FLOAT", 0.06, 0.0, 2.0, "DISTANCE")
    glyph_size = b.input("Glyph Size", "FLOAT", 0.7, 0.01, 20.0, "DISTANCE")
    panel_material = b.input("Panel", "MATERIAL", context.material("Sign Glow"))
    glyph_material = b.input("Glyphs", "MATERIAL", context.material("Sign Glyph"))
    frame_material = b.input("Frame", "MATERIAL", context.material("Dark Steel"))

    panel = b.node("GeometryNodeMeshCube", Size=b.combine(width, 0.08, height)).out
    frame = b.node("GeometryNodeMeshCube", Size=b.combine(b.math("ADD", width, b.math("MULTIPLY", bezel, 2.0)), 0.12, b.math("ADD", height, b.math("MULTIPLY", bezel, 2.0)))).out
    frame = b.transform(frame, translation=(0.0, 0.03, 0.0))

    letters = b.node("GeometryNodeStringToCurves", String=text, Size=glyph_size, Align_X="Center", Align_Y="Middle")["Curve Instances"]
    letters = b.realize(letters)
    filled = b.node("GeometryNodeFillCurve", Curve=letters, Mode="N-gons").out
    raised = b.node("GeometryNodeExtrudeMesh", props={"mode": "FACES"}, Mesh=filled, Offset=(0.0, 0.0, 0.03), Individual=False).out
    horizontal_glyphs = b.transform(raised, rotation=(1.5708, 0.0, 0.0))
    vertical_glyphs = b.transform(raised, rotation=(1.5708, 1.5708, 0.0))
    glyphs = b.switch(vertical, horizontal_glyphs, vertical_glyphs)
    glyphs = b.transform(glyphs, translation=(0.0, -0.045, 0.0))

    b.output("Geometry", "GEOMETRY", b.join(b.set_material(panel, panel_material), b.set_material(frame, frame_material), b.set_material(glyphs, glyph_material)))
