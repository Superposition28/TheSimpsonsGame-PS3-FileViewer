"""Resource parsers - backward compatibility module.

All parsers have been moved to the parsers package for better modularity.
This module re-exports them for backward compatibility.
"""
from .parsers import (
    parse_cec,
    parse_tob,
    parse_shk,
    parse_lighttoc,
    parse_metamodel,
    parse_simgroup,
    parse_rw_stream,
    parse_graph,
    #parse_ears_mesh,
    parse_preinstanced,
    parse_ears_mesh_unified,
)

__all__ = [
    "parse_cec",
    "parse_tob",
    "parse_shk",
    "parse_lighttoc",
    "parse_metamodel",
    "parse_simgroup",
    "parse_rw_stream",
    "parse_graph",
    #"parse_ears_mesh",
    "parse_preinstanced",
    "parse_ears_mesh_unified",
]
