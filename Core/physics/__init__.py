"""
Core.physics -- simulations built from geometry nodes, for any world.

Importing the package registers every ``Physics.*`` asset:

membrane   a pressurised elastic skin on Blender's native XPBD solver
           (water balloons, jelly bodies) with collider contact and an
           incompressible, heavy content
fluid      FLIP liquid on a staggered MAC grid: solids, sub-stepping,
           ballistic flight of free-falling drops and the liquid surface
liquid     per-particle liquid materials, so different liquids share a grid
hinge      a rigid body turning about a fixed axle that holds liquid in a
           cavity and pours it out (shishi-odoshi, water wheel buckets)
ground     the analytic ground plane taken from an object

Every group takes world-space geometry and seconds; state that lives from
frame to frame belongs to the caller's simulation zone.  ``GRAVITY`` is the
default of every gravity input.
"""
GRAVITY = (0.0, 0.0, -9.81)

from . import membrane, liquid, fluid, hinge, ground  # noqa: E402,F401
