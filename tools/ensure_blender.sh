#!/usr/bin/env bash
# ALTH-META · Instala Blender (bpy) sin interfaz y deja el comando `alth-python`.
# Es idempotente: si Blender ya importa, sale en segundos.
# Nunca termina con error a menos que se llame con --strict.
#
#   bash tools/ensure_blender.sh            # instala o verifica, muestra el resultado
#   bash tools/ensure_blender.sh --strict   # igual, pero sale con 1 si no quedó listo
#   bash tools/ensure_blender.sh --hook     # modo SessionStart: solo corre en la nube

STRICT=0; HOOK=0
for a in "$@"; do
  case "$a" in --strict) STRICT=1 ;; --hook) HOOK=1 ;; esac
done

if [ "$HOOK" = 1 ] && [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then exit 0; fi

PREFIX="${ALTH_PREFIX:-/opt/alth}"
if ! mkdir -p "$PREFIX" 2>/dev/null || [ ! -w "$PREFIX" ]; then PREFIX="$HOME/.alth"; mkdir -p "$PREFIX"; fi
BIN_DIR=/usr/local/bin; [ -w "$BIN_DIR" ] || { BIN_DIR="$HOME/.local/bin"; mkdir -p "$BIN_DIR"; }
LOG="${ALTH_LOG:-/tmp/alth-install.log}"
PRIMARY="bpy==5.2.2";  PRIMARY_PY=3.13
FALLBACK="bpy==4.5.14"; FALLBACK_PY=3.11

log() { echo "[alth] $*" | tee -a "$LOG"; }

ready() { "$PREFIX/bin/python" -c "import bpy" >/dev/null 2>&1; }

link() {
  ln -sf "$PREFIX/bin/python" "$BIN_DIR/alth-python" 2>/dev/null
  log "Listo: $("$PREFIX/bin/python" -c 'import bpy; print("Blender", bpy.app.version_string)' 2>/dev/null) · comando: $BIN_DIR/alth-python"
}

# Una sola instalación a la vez (el hook y Claude pueden llamarlo casi juntos).
exec 9>/tmp/alth-install.lock
if command -v flock >/dev/null 2>&1; then flock 9; fi

if ready; then link; exit 0; fi

# Librerías del sistema que carga Blender. La imagen de Claude Code ya las trae.
LIBS="libxrender1 libxxf86vm1 libxfixes3 libxi6 libxkbcommon0 libsm6 libgl1 libegl1"
if ! dpkg -s $LIBS >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
  log "Instalando librerías del sistema…"
  (apt-get update -qq && apt-get install -y -qq --no-install-recommends $LIBS) >>"$LOG" 2>&1 || log "apt falló; sigo"
fi

install_with() {  # $1 = versión de Python, $2 = paquete bpy
  local py="$1" pkg="$2"
  rm -rf "$PREFIX"; mkdir -p "$PREFIX"
  if command -v uv >/dev/null 2>&1; then
    log "Creando entorno Python $py con uv e instalando $pkg (~400 MB)…"
    uv venv -q --python "$py" "$PREFIX" >>"$LOG" 2>&1 \
      && uv pip install -q --python "$PREFIX/bin/python" "$pkg" pillow numpy >>"$LOG" 2>&1 \
      && ready && return 0
    log "uv no lo logró; intento con pip"
    rm -rf "$PREFIX"; mkdir -p "$PREFIX"
  fi
  command -v "python$py" >/dev/null 2>&1 || { log "No hay python$py"; return 1; }
  "python$py" -m venv "$PREFIX" >>"$LOG" 2>&1 \
    && "$PREFIX/bin/pip" install -q --no-cache-dir "$pkg" pillow numpy >>"$LOG" 2>&1 \
    && ready
}

START=$(date +%s)
if install_with "$PRIMARY_PY" "$PRIMARY" || install_with "$FALLBACK_PY" "$FALLBACK"; then
  log "Instalación terminada en $(( $(date +%s) - START )) s"
  link; exit 0
fi

log "No se pudo instalar Blender. Revisa $LOG (últimas líneas abajo)."
tail -n 15 "$LOG" 2>/dev/null
[ "$STRICT" = 1 ] && exit 1
exit 0
