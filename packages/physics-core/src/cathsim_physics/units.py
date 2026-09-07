"""Unit system for CathSim LA.

The whole project uses ONE consistent unit system.  Never introduce a
dimensionless "magic number" into physics code - every quantity below carries
its unit in the identifier or in the docstring of the function that uses it.

===========  =========================  ==========================
Quantity     Unit                       Typical identifier suffix
===========  =========================  ==========================
length       millimetre                 ``_mm``
time         second                     ``_s``
force        newton                     ``_n``
moment       newton-millimetre          ``_n_mm``
stress       megapascal (= N/mm^2)      ``_mpa``
angle        radian                     ``_rad``
curvature    1/millimetre               ``_per_mm``
bend/twist   newton-millimetre^2        ``_n_mm2``
stiffness
axial        newton                     ``_n``
stiffness
===========  =========================  ==========================

Derived relations used throughout the code base::

    EI [N mm^2] = E [MPa = N/mm^2] * I [mm^4]
    GJ [N mm^2] = G [MPa]          * J [mm^4]
    EA [N]      = E [MPa]          * A [mm^2]
    G  [MPa]    = E / (2 (1 + nu))

For a solid circular cross-section of diameter d [mm]::

    A = pi d^2 / 4          [mm^2]
    I = pi d^4 / 64         [mm^4]
    J = pi d^4 / 32         [mm^4]      (= 2 I)

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import math

#: Standard gravity expressed in the project unit system [mm/s^2].
GRAVITY_MM_PER_S2 = 9806.65

#: Conversion helpers.  Kept as functions (not constants) so that call sites
#: read as an explicit unit conversion rather than an unexplained factor.


def deg_to_rad(angle_deg: float) -> float:
    """Convert an angle from degrees (UI) to radians (physics core)."""
    return angle_deg * math.pi / 180.0


def rad_to_deg(angle_rad: float) -> float:
    """Convert an angle from radians (physics core) to degrees (UI)."""
    return angle_rad * 180.0 / math.pi


def circular_area_mm2(diameter_mm: float) -> float:
    """Cross-sectional area A [mm^2] of a solid circular section."""
    return math.pi * diameter_mm**2 / 4.0


def circular_second_moment_mm4(diameter_mm: float) -> float:
    """Second moment of area I [mm^4] of a solid circular section."""
    return math.pi * diameter_mm**4 / 64.0


def circular_polar_moment_mm4(diameter_mm: float) -> float:
    """Polar second moment J [mm^4] of a solid circular section (= 2 I)."""
    return math.pi * diameter_mm**4 / 32.0


def shear_modulus_mpa(youngs_modulus_mpa: float, poisson_ratio: float) -> float:
    """Isotropic shear modulus G [MPa] from E [MPa] and Poisson ratio nu [-]."""
    return youngs_modulus_mpa / (2.0 * (1.0 + poisson_ratio))
