"""ALTH-META · ropa reusable para personajes.

Cada función de aquí recibe `piezas` (el dict de `personaje.plan()["piezas"]`, o el de
`personaje.construir()` armado sobre las mismas medidas) y devuelve la lista de objetos que
arma. Los ayudantes (`radio_perfil`, `superficie_torso`) sirven para pegar cualquier prenda a la
tela sin que flote ni se entierre — eso es lo reusable de verdad entre personajes.

Una prenda NUEVA (otro corte, otro disfraz) normalmente no sale sola de `traje_formal`: necesita
su propia función en este archivo, reusando estos mismos ayudantes y el mismo patrón (perfil del
torso/pierna inflado unos milímetros, placas pegadas con `superficie_torso`, puños/dobladillos
con `anillo` en vez de un escalón en el perfil).
"""
from __future__ import annotations

import math


def radio_perfil(perfil, z_relativo):
    """Radio (antes del óvalo) de un perfil de alth.torno a esa altura, interpolando entre anillos."""
    for (r0, z0), (r1, z1) in zip(perfil, perfil[1:]):
        if z0 <= z_relativo <= z1:
            return r0 + (r1 - r0) * (z_relativo - z0) / (z1 - z0)
    return perfil[0][0] if z_relativo < perfil[0][1] else perfil[-1][0]


def superficie_torso(pieza_torso, z_mundo, embebe=0.15):
    """Y de la superficie de la tela sobre el torso a esa altura z (mundo), para pegar placas
    (cuello, solapas, corbata, botones) sin que floten ni se entierren."""
    z_rel = z_mundo - pieza_torso["pos"][2]
    r = radio_perfil(pieza_torso["perfil"], z_rel)
    ovalo_y = pieza_torso["ovalo"][1] if pieza_torso.get("ovalo") else 1.0
    return pieza_torso["pos"][1] - r * ovalo_y + embebe


def traje_formal(piezas, prefijo, *, camisa, chaleco, corbata, boton, pantalon,
                  grosor=0.35, grosor_ropa=0.9):
    """El traje de Theo (joven_rubio): chaleco con abertura en V (cuello de camisa + solapas +
    corbata + botones), mangas con puño de anillo, pantalón amplio con dobladillo de anillo,
    cintura. Para el mismo corte en otro personaje, basta con pasar otros colores."""
    from . import caja, torno, anillo  # atributos del paquete alth (definidos en __init__.py)

    objs = []
    torso = piezas["torso"]
    z_cuello = torso["pos"][2] + torso["perfil"][-1][1]

    collar = torno(f"{prefijo}_collar", [(13.6, 0.0), (14.2, 0.5), (12.6, 1.6)], segmentos=10,
                   color=camisa, alternar=False, ruido_r=0, ruido_z=0, pos=(0.0, 0.0, z_cuello - 1.5))
    objs.append(collar)

    torso_perfil = [(r + grosor, z) for r, z in torso["perfil"]]
    chaleco_obj = torno(f"{prefijo}_chaleco", torso_perfil, segmentos=12, color=chaleco, alternar=False,
                        ruido_r=0, ruido_z=0, ovalo=torso.get("ovalo"), pos=torso["pos"])
    objs.append(chaleco_obj)

    torso_infl = {"pos": torso["pos"], "perfil": torso_perfil, "ovalo": torso.get("ovalo")}

    z_v_arriba = z_cuello - 2.2   # justo bajo el cuello de camisa
    z_v_abajo = torso["pos"][2] + 0.8   # casi hasta la cintura

    # cuello de camisa blanco visible en la abertura en V: franjas que se angostan hacia abajo
    ancho_v = (9.5, 8.2, 6.8, 5.2, 3.6, 2.4)
    for i, ancho in enumerate(ancho_v):
        t = i / (len(ancho_v) - 1)
        z_franja = z_v_arriba + (z_v_abajo - z_v_arriba) * t
        alto_franja = (z_v_arriba - z_v_abajo) / (len(ancho_v) - 1) + 0.6
        franja = caja(f"{prefijo}_camisa_v_{i}", (ancho, 0.3, alto_franja),
                      pos=(0.0, superficie_torso(torso_infl, z_franja), z_franja),
                      color=camisa, biselar=False, apoyada=False)
        objs.append(franja)

    # solapas: dos paños del chaleco que se abren en la punta de la V
    for lado, s in (("izq", -1), ("der", 1)):
        solapa = caja(f"{prefijo}_solapa_{lado}", (4.2, 0.35, 6.5),
                      pos=(s * 4.6, superficie_torso(torso_infl, z_v_arriba + 1.0) - 0.1, z_v_arriba + 1.0),
                      color=chaleco, biselar=False, apoyada=False)
        solapa.rotation_euler = (0.0, 0.0, math.radians(-s * 22))
        objs.append(solapa)

    z_corbata = (z_v_arriba + z_v_abajo) / 2
    corbata_obj = caja(f"{prefijo}_corbata", (2.6, 0.35, z_v_arriba - z_v_abajo + 1.5),
                       pos=(0.0, superficie_torso(torso_infl, z_corbata, 0.15 + 0.12), z_corbata),
                       color=corbata, biselar=False, apoyada=False)
    objs.append(corbata_obj)

    for i, t in enumerate((0.45, 0.65, 0.85)):  # repartidos a lo largo de toda la abertura
        z_boton = z_v_arriba + (z_v_abajo - z_v_arriba) * t
        boton_obj = caja(f"{prefijo}_boton_{i}", (1.3, 0.4, 1.3),
                         pos=(0.0, superficie_torso(torso_infl, z_boton), z_boton),
                         color=boton, apoyada=False)
        objs.append(boton_obj)

    # mangas anchas (puño: anillo, no disco)
    for lado, s in (("izq", -1), ("der", 1)):
        b = piezas[f"brazo_{lado}"]
        r0, r1, largo = b["r0"] + grosor_ropa, b["r1"] + grosor_ropa, b["largo"]
        manga = torno(f"{prefijo}_manga_{lado}", [(r0, 0.0), (r1, largo)], segmentos=8, color=camisa,
                     alternar=False, ruido_r=0, ruido_z=0, pos=b["pos"])
        manga.rotation_euler = tuple(math.radians(v) for v in b["rot"])
        objs.append(manga)

        x_puno = b["pos"][0] + s * (largo + 0.3)  # el eje +Z local de la manga apunta a ±X del mundo
        puno = anillo(f"{prefijo}_puno_{lado}", radio=r1 * 0.95, grosor=2.0, segmentos=10, lados=4,
                     color=camisa, pos=(x_puno, b["pos"][1], b["pos"][2]), rot=(0.0, 90.0, 0.0))
        objs.append(puno)

    # pantalón amplio (dobladillo: anillo, no disco)
    for lado, s in (("izq", -1), ("der", 1)):
        pierna = piezas[f"pierna_{lado}"]
        base_infl = [(r + grosor_ropa, z) for r, z in pierna["perfil"]]
        r0 = base_infl[0][0]
        perfil = [(r0 * 0.97, -1.5)] + base_infl
        pantalon_obj = torno(f"{prefijo}_pantalon_{lado}", perfil, segmentos=10, color=pantalon,
                             alternar=False, ruido_r=0, ruido_z=0, ovalo=pierna.get("ovalo"), pos=pierna["pos"])
        objs.append(pantalon_obj)

        z_dobladillo = pierna["pos"][2] + 1.6
        dobladillo = anillo(f"{prefijo}_dobladillo_{lado}", radio=r0 * 1.05, grosor=2.4, segmentos=10, lados=4,
                            color=pantalon, escala=(1.0, pierna.get("ovalo", (1.0, 1.0))[1], 1.0),
                            pos=(pierna["pos"][0], pierna["pos"][1], z_dobladillo))
        objs.append(dobladillo)

    # cintura: cubre la pelvis (piel visible entre el chaleco y el pantalón)
    cadera = piezas["pelvis"]
    cintura = caja(f"{prefijo}_pantalon_cadera",
                   tuple(v + 2 * grosor_ropa for v in cadera["tam"][:2]) + (cadera["tam"][2],),
                   pos=cadera["pos"], color=pantalon, apoyada=True)
    objs.append(cintura)

    return objs
