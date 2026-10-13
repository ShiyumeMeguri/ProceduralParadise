# Rain Garden (雨花之庭) — port in progress

Goal: rebuild the owner's reference painting, a fractal "rain garden"
atrium, as a fully procedural, free-camera 3D scene. Where the painting's
structure is impossible in 3D, design a plausible 3D space that follows the
painting's fractal logic. The result becomes a realm of FractalWorld and
its kit an asset library (`--asset-library`).

The reference image is **not** in the repository. Ask the owner for it.

`Legacy/` holds the earlier standalone pipeline, which builds and renders
the whole scene in Blender 5.3. It was tuned in Cycles. It is the source
of truth for this port. Delete `Legacy/` and this file once the port is
complete.

Legacy usage:

```
blender -b -P Legacy/build.py -- --library <dir> --palette palette.json --layout layout.json --scene <file.blend> [--preset blockout|preview|compare|final] [--render <png>]
```

## Done on this branch (not yet run in Blender)

- `Core/shaders.py`: `thin_glass()` is extracted from `glass_mat`.
- `Core/assetlibrary.py` and `build.py --asset-library DIR`: export the
  kit of the built scene folder, one `.blend` per category, with catalogs.
- `RainGarden/__init__.py`: `REALM` comes from `Realm.json`, which is
  still to be written.
- `RainGarden/values.py`.
- `RainGarden/sky.py`: the sun lamp and the sky world. This ports
  `Legacy/rain_garden/look.py`.
- `Kit/shapes.py`: shared construction helpers.
- `Kit/materials.py`: the data-driven EEVEE material library (shader types
  below).
- `Kit/architecture.py`: 14 assets.
- `Kit/water.py`: 6 assets. Bodies of water already carry `thickness`.

## To do

1. Port the remaining Legacy modules, in the style of `architecture.py`
   and `water.py`:
   - `Kit/lights.py`: crystal_pendant, hanging_chain, hanging_lighthouse,
     ornate_lantern.
   - `Kit/plants.py`: branching_tree, fan_coral, potted_tree.
   - `Kit/creatures.py`: dove, fish_school, jellyfish, manta_ray,
     reef_fish.
   - `Kit/decorative.py`: crystal_parapet, cube_seat, glass_wave,
     lounge_bench, plinth_planter, sign_panel.

   `Kit/__init__.py` already imports these four modules. Asset names
   follow `RainGarden.<Category>.<PascalName>`.
2. Write `Realm.json` from `Legacy/palette.json`, using the material rules
   below.
3. Write `scenes.py`, a scene interpreter like
   `CrystalFantasy/scenes.py`.
4. Write `Scenes/Atrium/{scene.json, shots/Atrium.json, README.md}` from
   `Legacy/layout.json`.
5. Verify in Blender 5.3 headless, with the EEVEE engine only:
   - Every object evaluates to non-empty geometry with no modifier
     warnings.
   - Per-object vertex counts and bounds match a Legacy build.
   - Lathed parts have outward normals.
   - Refractive bodies carry `thickness`.
   - `--asset-library` writes loadable files.
6. Render the shot and the free views in EEVEE, retune the look, and work
   on the known gaps.
7. Update `FractalWorld/README.md` and the root `README.md`.

## Legacy DSL → `Core.gn.GN`

| Legacy | Core |
|---|---|
| `b.input(name, kind, default, min, max, subtype, panel=b.panel("X"))` | `g.inp(name, stype, default, min, max, subtype, panel="X")` |
| `b.output("Geometry", "GEOMETRY", v)` | `g.result(v)` |
| `.out` / `b.combine` / `b.separate` | `.o` / `g.vec` / `g.sep` (or `.x .y .z`) |
| `vmath("SCALE", v, s)` | `v * s` or `g.vmath("SCALE", v, scale=s)` |
| `transform(translation=, rotation=, scale=)` | `g.transform(geo, t=, r=, s=)` (wrap a vector rotation socket in `shapes.euler`) |
| `set_material` / `set_position(position=, offset=)` | `g.mat` / `g.set_pos(geo, pos=, offset=)` |
| `instance(points, inst, rotation, scale, selection, pick, instance_index)` | `g.iop(points, inst, rot=, scale=, sel=, pick=, index=)` |
| `random(lo, hi, seed, identifier=, data_type=)` | `g.random(lo, hi, seed, ID=, dtype=)` (BOOLEAN needs `Probability`: write the node) |
| `compare(a, b, op)` (default **GREATER_THAN**) | `g.compare(a, b, op)` (default **LESS_THAN**) |
| `boolean("AND"/"NOT", ...)` | `g.bool_and` / `g.bool_not` |
| `curve_to_mesh(c, p)` (caps default **False**) | `g.sweep(c, p, caps)` (default **True**) |
| `curve_to_mesh_by_radius(c, p)` | `g.n("GeometryNodeCurveToMesh", Curve=c, Profile_Curve=p, Scale=g.n("GeometryNodeInputRadius").o)` |
| `align_z(v, axis=)` / `store(..., data_type=)` | `g.align_rotation(v, axis=)` / `g.store(..., dtype, domain)` |
| `context.require("Name")` | `get_asset("RainGarden.<Category>.<Name>")` |
| `context.material("White Stone")` | `M.get("RainGarden.WhiteStone")` |
| `shapes.sweep` / `vertical_ribbon` / `fill_at_height` | `shapes.framed_sweep` / `hanging_ribbon` / `fill_at_height` |
| Mesh Boolean | `g.n("GeometryNodeMeshBoolean", props={"operation": ..., "solver": "MANIFOLD"})` + assign a list to `"Mesh 2"` |

- **Lathes**: Legacy `shapes.lathe` takes its profile top to bottom.
  `g.lathe(pts)` takes `(r, z)` bottom to top, from the axis out, for
  outward normals. Reverse these Legacy profiles:
  - the lighthouse's SPIRE, ROOF, LANTERN_ROOM, GALLERY, TOP_RING, DRUM,
    BOTTOM_RING, FUNNEL, NOZZLE, DRUM_WATER and its statue (scale through
    `g.lathe(..., scale=)`);
  - the lantern's FINIAL, CAP, TOP_RING, BODY, BOTTOM_RING, BASE;
  - the pendant drop and bell, and the jellyfish bell.

  The potted tree's pot is already bottom to top. Use
  `shapes.unit_lathe(profile, pot_radius, pot_height)`.
- **Fish School**: make it independent of instance order. Use one `iop`
  per variant with `sel = (choice == k)`, then join.
- **EEVEE thickness**: wrap every closed refractive body in
  `shapes.measured(mesh, longest)`. Pool, basin and whale water already
  do. Still to do: the lighthouse drum water, the crystal parapet shards
  and the glass wave.
- **Angles**: scene data is in degrees, and ANGLE sockets convert it. The
  Legacy layout stores radians for these inputs:
  - Crystal Parapet: Outward Lean, Lean Jitter.
  - Dove: Wing Beat.
  - Fish School: Heading Jitter.
  - Glass Vault: Sweep.
  - Leaning Frame: Lean, Rake, Roof Slope.
  - Fan Coral: Spread.
  - Reef Fish: Tail Fork.
  - Ribbon Cascade: Twist.
  - Waterfall Curtain: Twist.
  - Water Jet: Spike Spread.
- **Tower Pier lettering**: `Inlay Text` and `Upper Band Text` now
  default to empty. The scene passes the painting's letters, which were
  the Legacy defaults `LAYRE` and `AZURE`.

## Materials (`Realm.json` `"materials"`)

Each entry is keyed `RainGarden.<Legacy name without spaces>` and holds
`{"shader": type, ...parameters, "description"}`. A scene's `"materials"`
section, `{"RainGarden.X": {parameter: value}}`, overrides it.

EEVEE refracts through one layer only. Glass shells are therefore
transparent plus Fresnel gloss, and only bodies with `thickness` refract.

| Legacy shader | Realm shader | Conversion |
|---|---|---|
| `clear_glass` | `thin_glass` | `color` = tint, `roughness`, `ior` 1.5, `reflect` = reflectivity; drop `reflection_blend` and `base_reflection` |
| `water` | `refractive` | keep `base_color` (tint), `roughness`, `ior`, `specular`, `absorption_*`, `ripple_*`, `reflection_tint`, `glow_color`, `surface_glow`, and `glow_strength`, which is now emission per metre of `thickness`; drop `shadow_*` |
| `crystal` | `crystal` | keep `tint_stops`, `transmission`, `roughness`, `ior`, `inner_glow`; drop `shadow_*` |
| `iridescent_glass` | `iridescent_glass` | `color` = base_color, `roughness`, `ior`, `film_scale`, `sheen_*`; write the Legacy default `sheen_stops` into the data; drop `film_min`, `film_max`, `thin_film_ior`, `transmission`, `shadow_*` |
| `principled` "Wave Glass" | `refractive` | `base_color`, `ior` 1.45, `roughness` 0.02, `glow_color` = emission_color, `surface_glow` = emission_strength |
| everything else | unchanged | `principled` with `shadow_transparent` gets dithered rendering and transparent shadows |

## Scene

- **Camera**, solved from the painting:
  - 1792×1024, f = 900 px (18.08 mm on a 36 mm sensor);
  - location (0, 0, 1.7);
  - yaw −57.1°, pitch +10.266°, roll 0;
  - +Y north, +X east, Z up, metres.
- **Shot render**: EEVEE, view transform Standard, exposure −0.75.
- **Shot look**:
  - bloom: threshold 0.8, size 0.8, strength 0.5, smoothness 0.35;
  - lift (0.95, 0.99, 1.08), gamma (0.97, 1.0, 1.04);
  - hue/saturation: saturation 1.18.
- **Sun and sky**: `sun` and `sky` in `Legacy/layout.json`, read by
  `sky.py`. In `sun`, `strength` becomes `power` and `angle_degrees`
  becomes `angle`.
- **Guides**: Legacy `curves` become `guides`. An item's `curve` makes
  that guide's data the object's own curve. An OBJECT input names a
  guide.
- **Items**: Legacy `orient {x, z}` is kept. Legacy `rotation_degrees`
  becomes `rot`.
- **Collections**: named `Atrium.<Collection path with dots>`.
- **Free views** (location → target, lens):
  - `overview`: (−6, −12, 28) → (22, 18, 6), lens 18;
  - `pool`: (8, −4, 1.6) → (28, 10, 8), lens 24;
  - `east_facade`: (12, 18, 6) → (36, 8, 10), lens 20.

## Known gaps

These are from the last Legacy render compared with the painting:

- The arches should be thick white box girders.
- The lighthouse crown ornaments are missing.
- The crystal band should be bluer and denser.
- The right-hand niwaki tree should be darker and sparser.
- The west leaning pillars (rake 0.8, height 16) are unchecked.
- Sign sizes are unchecked.
- The pit / light well needs a design.
- The last pool restructure is unchecked.
- The whale look needs work.
- The whole look must be retuned under EEVEE.

## Conventions for whoever continues

- EEVEE only: no Cycles settings.
- `git add` files by name.
- Commit messages: a single Chinese line of at most 50 characters, with
  no body, no AI attribution and no game names.
- No local absolute paths in files or commit messages.
