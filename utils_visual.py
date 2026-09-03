# -*- coding: utf-8 -*-
"""Módulo de utilitários visuais e cálculos de contraste para o Senai LabFashion IA."""

def hex_to_rgb(hex_str: str) -> tuple:
    """Converte uma string hexadecimal (#RRGGBB ou #RGB) em tupla RGB (R, G, B)."""
    hex_clean = hex_str.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) != 6:
        return (0, 71, 171)  # Fallback para o azul primário do Senai
    return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))


def calcular_cor_texto_contraste(hex_cor: str) -> str:
    """Calcula a luminância da cor de fundo (fórmula padrão WCAG: 0.299*R + 0.587*G + 0.114*B).

    Retorna '#000000' (preto) se a luminância for alta (> 150) ou '#FFFFFF' (branco) se for baixa (<= 150).
    """
    r, g, b = hex_to_rgb(hex_cor)
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    if luminancia > 150:
        return "#000000"
    return "#FFFFFF"
