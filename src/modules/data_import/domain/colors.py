from typing import Optional

PALETTE = {
    "rojo": (220, 38, 38),
    "naranja": (237, 125, 49),
    "amarillo": (255, 220, 0),
    "verde": (112, 173, 71),
    "celeste": (91, 155, 213),
    "azul": (68, 114, 196),
    "morado": (126, 87, 194),
    "rosado": (236, 112, 160),
    "gris": (165, 165, 165),
    "marron": (150, 100, 60),
    "negro": (20, 20, 20),
}


def color_name(rgb: Optional[str]) -> Optional[str]:
    if not rgb or len(rgb) != 6:
        return None
    r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    if min(r, g, b) > 235:
        return "blanco"
    return min(PALETTE, key=lambda name: sum((x - y) ** 2 for x, y in zip(PALETTE[name], (r, g, b))))
