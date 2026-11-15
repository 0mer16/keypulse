"""Lighting effects. Each effect module registers itself in EFFECTS."""
from .typetext import TypeTextEffect
from .visualizer import VisualizerEffect

EFFECTS = {cls.id: cls for cls in (VisualizerEffect, TypeTextEffect)}
