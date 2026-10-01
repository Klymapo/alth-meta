# Auditoría visual: el gate de aprobación

Decisión del dueño (1 oct 2026): **la comparación de imágenes decide si un asset se aprueba**. Ya no
hay "decisión visual pendiente": si la auditoría da FAIL no se publica, aunque alguien ponga la etiqueta
`aprobado`. Todo es código (numpy/scipy/Pillow), sin modelos ni IA, y corre en un runner gratuito.

## Flujo

```
crear_asset.py → hoja final (4 vistas) → auditoria_visual.py ─┬─ PASS y sin faltantes → publicar_pr.sh → PR → el dueño fusiona
                                                              └─ FAIL / faltantes     → comentario con la evidencia, job en rojo
```

| Pieza | Qué hace |
|---|---|
| `tools/mascaras.py` | Una sola forma de sacar la figura para referencia y render: fondo conectado al borde + sombra que se desvanece + sombra de piso pegada. También la usa el proveedor de Kaggle. |
| `tools/auditoria_visual.py` | Compara y decide. Deja `auditoria.json` y `comparacion.png` (azul = sólo referencia, naranja = sólo modelo, gris = ambos). Salida 0 PASS · 1 FAIL · 2 entrada inválida. |
| `spec/auditoria_visual.json` | Umbrales, con el porqué de cada uno y si están calibrados. |
| `tools/calibrar_auditoria.py` + `kb/pares_auditoria.json` | Recalcula los umbrales con pares etiquetados aprobado/rechazado (J de Youden por medida). |
| `tools/crear_asset.py` | Audita la hoja final. Estados: `APROBADO_POR_AUDITORIA` (0), `VERIFICACION_FALLIDA` (1), `AUDITORIA_FALLIDA` (3), `FALTANTES` (4). |
| `tools/publicar.py` | Reconstruye en modo final **fuera de assets/**, verifica, vuelve a auditar y sólo entonces copia. Nunca escribe en `assets/joven_rubio/`; comprueba el SHA-256 de Theo Alpha antes y después. |
| `tools/publicar_pr.sh` | Rama `publicar/<nombre>-issue-N` y PR. Nunca empuja a `main`. |

## Cómo compara

1. **Encuadre fijo**: cada figura se recorta a su caja, se escala a la misma altura y se centra por su
   centroide. Se compara forma, no tamaño ni posición.
2. **Medidas que vetan** (un FAIL basta, el puntaje nunca compensa):

   | medida | qué detecta |
   |---|---|
   | `silueta_iou` | si ocupan el mismo lugar (único umbral publicado: 0.8) |
   | `contorno_p95`, `contorno_chamfer` | desvíos del borde en algún tramo (hoja, asa, orejas) |
   | `compacidad` | inercia global (primer momento de Hu) |
   | `bandas_media` | proporción a lo alto (ancho por franja) |
   | `aspecto` | ancho/alto de la caja |
   | `redondez_llenado`, `redondez_esquinas` | si el cuerpo (sin tallo ni hoja) es redondo o una caja de lados rectos: cuánto llena su caja y sus 4 esquinas |
   | `color_regiones` | color por celda de una rejilla 4×3 (Lab con L* a la mitad: la luz del render no es la de la ref) |
   | `color_dominante` | los 6 colores dominantes emparejados |
   | `supera_aprobado` | si ya hay un asset aprobado, reemplazarlo exige superarlo: más IoU y menos contorno p95 que él (`no_peor_que_aprobado` queda como dato) |

   Informativas: Dice, Hu completos, banda máxima, SSIM de luminancia.
3. **Vista**: se audita cada vista del render y se usa la más parecida; con `--vista` se fuerza una y se
   avisa si otra se parece más.

## Primer veredicto del dueño (1 oct 2026)

La manzana que genera la línea **superaba a la aprobada** en silueta (IoU 0.861 vs 0.837), contorno
(p95 0.079 vs 0.140) y color, y la auditoría la dejaba pasar. El dueño la rechazó: **parece una caja**
(hombros planos, lados rectos, pico arriba, muesca a la derecha). Silueta y color no miden eso; por eso
se añadieron las dos medidas de redondez y la manzana quedó en `kb/pares/` como primer par rechazado
(`test_manzana_rechazada_por_el_dueno_falla_por_redondez`).

## Estado de los umbrales (1 oct 2026): provisionales

Puestos con los 5 assets aprobados del repo: manzana y lata contra sus infografías (2 positivos) y cada
referencia contra los otros objetos, más la manzana rechazada (9 negativos). Clasifican bien los 11 pares (prueba
`test_matriz_real_aprobados_pasan_y_cruces_fallan`), pero el margen es corto:

- color entre cilindros: lata contra taza da 11.1 en `color_dominante` (umbral 10.5);
- `contorno_p95` de la manzana aprobada: 0.140 (umbral 0.145), sobre todo por la hoja, más chica que la de la referencia.

Para que valgan hacen falta **pares difíciles etiquetados por el dueño**: el mismo objeto en versión
buena y mala (la manzana rechazada del 1 oct es el primero). Con al menos 10 aprobados y 10 rechazados,
`python3 tools/calibrar_auditoria.py --escribir` los recalcula y marca `calibrado: true` sólo si la regla
completa no se equivoca en ningún par.

## Límites conocidos

- Mide la figura completa. Detalles chicos (dedos separados, botones) no los ve: por eso una capacidad
  faltante (`FALTANTES`) impide aprobar aunque la silueta pase. Para personajes hará falta auditar por
  región (manos, cara), con su recorte.
- La referencia y el render tienen que mostrar la misma vista aproximada. Si la referencia es una foto
  en 3/4 desde arriba y la hoja no trae esa vista, la mejor vista disponible puede no alcanzar.

```bash
python3 tools/auditoria_visual.py --ref refs/infografias/objeto-01-manzana.png --recorte 0.52,0.1,1,1 \
    --hoja assets/manzana/final.png --aprobado assets/manzana/final.png --salida /tmp/aud
```
