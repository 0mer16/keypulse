"""Lighting effects. Each effect module registers itself in EFFECTS."""
from .visualizer import VisualizerEffect

EFFECTS = {cls.id: cls for cls in (VisualizerEffect,)}
