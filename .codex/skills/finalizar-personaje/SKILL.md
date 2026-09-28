---
name: finalizar-personaje
description: Finaliza un personaje ALTH-META ya iniciado con una ronda integral, pruebas de Blender, evidencia visual y aprobación humana. Úsala cuando pidan terminar, cerrar o llevar a versión final un personaje, especialmente Theo o joven_rubio, reduciendo llamadas de IA y evitando vueltas incrementales.
---

# Finalizar personaje ALTH-META

1. Leer `CLAUDE.md` y `docs/agentes/finalizar_personaje.md` completos.
2. Identificar el asset, su mejor rama verificada, sus referencias y su `brief_final.md`. No inventar un asset duplicado si el alias ya existe.
3. Confirmar que el trabajo ocurre en una rama de propuesta o `bucle/*`, nunca directamente en `main` antes de la aprobación.
4. Usar `tools/bucle.py` con una vuelta. El brief se incorpora automáticamente; no duplicarlo en `--nota`.
5. Mantener los cambios dentro de los archivos editables. No ampliar el alcance a módulos compartidos salvo autorización explícita.
6. Ejecutar build y pruebas deterministas. Entregar hoja, reporte, manifest y cambios al revisor visual.
7. Detenerse para decisión humana. No generar `final`, GLB ni commit aprobado por cuenta propia.

Para Theo, leer además `assets/joven_rubio/brief_final.md` y tratarlo como contrato obligatorio de la ronda.
