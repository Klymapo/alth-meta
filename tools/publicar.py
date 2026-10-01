"""Publica un asset APROBADO por el usuario (bloque T4 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/publicar.py .linea/crear/manzana --issue 12

La publicación va a una rama y entra a main por PR (tools/publicar_pr.sh); nunca directo a main.
Nada se escribe en assets/ hasta pasar DOS gates sobre la versión final:
  a. verificación técnica (cotas, paleta, flotantes, apoyo, tris);
  b. auditoría visual contra la referencia (tools/auditoria_visual.py), sin quedar peor que el asset
     aprobado anterior si existe. La auditoría decide; un FAIL no se publica aunque haya etiqueta.
Theo Alpha (assets/joven_rubio/theo_alpha.glb) está protegido: no se publica nada en su carpeta.
A partir de la receta revisada:
  1. reconstruye en modo FINAL en la carpeta de la corrida, audita, y sólo entonces copia a
     assets/<nombre>/: .glb (raíz ×0.01, Y-up), final.png (hoja de 4 vistas), spec.json (conserva el
     historial de la versión anterior) y la evidencia de la auditoría;
  2. reemplaza las filas del asset en data/medidas.csv con lo medido (aprobado=si);
  3. aprende: capacidades usadas → `dominada` con assets/<nombre>/final.png como evidencia;
  4. memoriza la huella de las 4 vistas (kb/huellas.json).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
MEDIDAS_CSV = RAIZ / "data" / "medidas.csv"
PROTEGIDO = RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb"
PROTEGIDO_SHA256 = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"


class PublicacionRechazada(RuntimeError):
    """No se publica: falló un gate. assets/ queda intacto."""


def _sha256(ruta: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def entrada_de(carpeta: Path) -> tuple[str, list | None]:
    """(imagen de referencia, recorte) con que se creó la corrida (resumen.json o entrada.json)."""
    for nombre in ("resumen.json", "entrada.json"):
        f = Path(carpeta) / nombre
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("imagen"):
                rec = d.get("recorte")
                if isinstance(rec, str):
                    rec = [float(x) for x in rec.split(",")] if rec else None
                return d["imagen"], rec
    raise PublicacionRechazada("no sé contra qué imagen auditar: falta resumen.json/entrada.json con 'imagen'")


def filas_medidas(receta: dict, dims_mm: dict, s0: float, fecha: str) -> list[dict]:
    """Filas de data/medidas.csv para las medidas que dio el usuario (las demás se derivan de la foto)."""
    k = receta["k"]
    out = []
    for d in receta["medidas_mm"].get("dadas") or ["ancho"]:
        if d not in dims_mm or not receta["medidas_mm"].get(d):
            continue
        real = receta["medidas_mm"][d] / (s0 * k)
        out.append({"asset": receta["nombre"], "categoria": receta["categoria"], "medida": d,
                    "real_mm": f"{real:.0f}", "alth_mm": f"{dims_mm[d]:.2f}",
                    "k_observado": f"{dims_mm[d] / (real * s0):.2f}", "aprobado": "si", "fecha": fecha})
    return out


def reemplazar_filas(nombre: str, nuevas: list[dict], ruta: Path = MEDIDAS_CSV) -> None:
    with ruta.open(encoding="utf-8", newline="") as fh:
        lector = csv.DictReader(fh)
        campos, filas = lector.fieldnames, [f for f in lector if f["asset"] != nombre]
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        w.writerows(filas + nuevas)


def publicar(carpeta: Path, issue: int | None = None, fecha: str | None = None) -> dict:
    import capacidades as cap
    import construir_receta as C
    import reconocer as rec
    import redimensionar as rd

    import auditoria_visual as AV

    carpeta = Path(carpeta)
    fecha = fecha or date.today().isoformat()
    receta = json.loads((carpeta / "receta.json").read_text(encoding="utf-8"))
    raiz_assets = (RAIZ / "assets").resolve()
    destino = (raiz_assets / str(receta.get("nombre") or "")).resolve()
    protegida = PROTEGIDO.parent.resolve()
    if (destino.parent != raiz_assets or destino == protegida or protegida in destino.parents
            or destino in protegida.parents):
        raise PublicacionRechazada(f"destino protegido o fuera de assets/<nombre>/: {destino}")
    sha_antes = _sha256(PROTEGIDO) if PROTEGIDO.exists() else None
    imagen, recorte = entrada_de(carpeta)
    previo = json.loads((destino / "spec.json").read_text(encoding="utf-8")) if (destino / "spec.json").exists() else {}
    # gate a: verificación técnica (exporta a la carpeta de la corrida, no a assets/)
    preparado = carpeta / "final" / "export"
    res = C.construir(receta, carpeta / "final", modo="final", exportar=preparado)
    if not res["ok"]:
        raise PublicacionRechazada(f"la versión final no pasa la verificación: {res['dif_dimensiones']}, "
                                   f"verificación {res['verificacion_ok']}")
    # gate b: auditoría visual de la versión final contra la referencia (y contra el aprobado anterior)
    aprobado = destino / "final.png"
    aud = AV.auditar_archivos(RAIZ / imagen if not Path(imagen).is_absolute() else imagen,
                              carpeta / "final" / "auditoria", tuple(recorte) if recorte else None,
                              hoja=res["hoja"], aprobado=aprobado if aprobado.exists() else None)
    if aud["decision"] != "PASS":
        raise PublicacionRechazada(f"la auditoría visual rechaza la versión final: {', '.join(aud['fallas'])} "
                                   f"(evidencia en {aud['evidencia']['comparacion']})")
    destino.mkdir(parents=True, exist_ok=True)
    for f in preparado.iterdir():
        shutil.copyfile(f, destino / f.name)
    shutil.copyfile(res["hoja"], destino / "final.png")
    shutil.copyfile(aud["evidencia"]["json"], destino / "auditoria.json")
    shutil.copyfile(aud["evidencia"]["comparacion"], destino / "auditoria_comparacion.png")
    spec = json.loads((destino / "spec.json").read_text(encoding="utf-8"))
    spec["historial"] = previo.get("historial", []) + [
        {"vuelta": "línea única", "nota": f"receta por código, auditoría visual PASS (vista {aud['vista']}, "
                                          f"IoU {aud['medidas']['silueta_iou']})"
                                          + (f", issue #{issue}" if issue else ""), "fecha": fecha}]
    spec["escala"] = {"version": "v2.0", "s0": json.loads((RAIZ / "spec" / "alth_spec.json").read_text())
                      ["escala_alpha"]["s0"]}
    (destino / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    glb = rd.revisar_glb(destino / f"{receta['nombre']}.glb", 0.01)
    if not glb["ok"]:
        raise RuntimeError(f"GLB mal exportado: {glb}")
    s0 = spec["escala"]["s0"]
    reemplazar_filas(receta["nombre"], filas_medidas(receta, res["dimensiones_mm"], s0, fecha))
    evidencia = str((destino / "final.png").relative_to(RAIZ))
    vocab = rec.cargar_vocab()
    registro = cap.cargar_registro()
    aprendidas = []
    for c in receta["origen"].get("capacidades", []):
        if c in vocab["capacidades"]:
            cap.aprender(registro, c, "dominada", f"usada en {receta['nombre']} aprobado"
                         + (f" (issue #{issue})" if issue else ""), [evidencia], vocab=vocab)
            aprendidas.append(c)
    cap.guardar_registro(registro)
    rec.memorizar(destino)
    if sha_antes and _sha256(PROTEGIDO) != sha_antes:
        raise PublicacionRechazada("theo_alpha.glb cambió durante la publicación: abortar sin commit")
    return {"auditoria": {"decision": aud["decision"], "vista": aud["vista"],
                          "supera_aprobado": aud.get("supera_aprobado")},"asset": str(destino.relative_to(RAIZ)), "glb": glb, "iou": res["iou"],
            "dimensiones_mm": res["dimensiones_mm"], "capacidades_aprendidas": aprendidas, "memorizado": True}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("carpeta", help="carpeta de la corrida revisada (receta.json)")
    p.add_argument("--issue", type=int, default=None)
    a = p.parse_args(argv)
    try:
        r = publicar(Path(a.carpeta), a.issue)
    except PublicacionRechazada as e:
        print(f"NO SE PUBLICA: {e}", file=sys.stderr)
        return 3
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
