"""Resource parsers package.

Provides modular parsers for different Simpsons Game resource types.
"""
from .cec_parser import parse_cec
from .tob_parser import parse_tob
from .shk_parser import parse_shk
from .lh2 import LH2Parser
from .lighttoc_parser import parse_lighttoc
from .metamodel_parser import parse_metamodel
from .simgroup_parser import parse_simgroup
from .rw_stream_parser import parse_rw_stream
from .graph_parser import parse_graph
from .preinstanced_parser import parse_preinstanced, parse_ears_mesh_unified
from .msb_parser import parse_msb

__all__ = [
    "parse_cec",
    "parse_tob",
    "parse_shk",
    "parse_lighttoc",
    "parse_metamodel",
    "parse_simgroup",
    "parse_rw_stream",
    "parse_graph",
    "parse_preinstanced",
    "parse_ears_mesh_unified",
    "parse_msb",
    "LH2Parser",
]
