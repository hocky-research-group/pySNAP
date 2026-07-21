from .star_polymer import make_star_polymer
from .linear_polymer import make_linear_polymer
from .ring_polymer import make_ring_polymer
from .comb_polymer import make_comb_polymer
from .grafted_colloid import make_grafted_colloid
from .patchy_colloid import make_patchy_colloid

MOLECULE_TEMPLATES = {
    "star_polymer": make_star_polymer,
    "linear_polymer": make_linear_polymer,
    "ring_polymer": make_ring_polymer,
    "comb_polymer": make_comb_polymer,
    "grafted_colloid": make_grafted_colloid,
    "patchy_colloid": make_patchy_colloid,
}
