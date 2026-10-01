#!/usr/bin/env bash
# Publica una corrida de la línea única POR PR (nunca push directo a main).
#
#   bash tools/publicar_pr.sh <carpeta-de-la-corrida> <issue> [ref-con-la-imagen]
#
# 1. Rama publicar/<nombre>-issue-<N> desde origin/<rama por defecto>.
# 2. tools/publicar.py: verificación técnica + auditoría visual de la versión final. Si un gate falla,
#    sale con 3, no hay commit ni rama, y el issue recibe el motivo.
# 3. Commit (assets/<nombre>, data/medidas.csv, kb, imagen de referencia) y push de la rama.
# 4. Abre el PR con el token del workflow. Si el repo no permite que Actions abra PRs, deja en el
#    issue el enlace para abrirlo con un clic. El dueño fusiona: eso es el release.
#
# Requiere: alth-python, git con identidad, GH_TOKEN, GITHUB_REPOSITORY. Theo Alpha se verifica antes
# y después (SHA-256 fijo en CLAUDE.md).
set -euo pipefail

carpeta="${1:?carpeta de la corrida}"
N="${2:?número de issue}"
img_ref="${3:-}"
base="${BASE_BRANCH:-main}"
repo="${GITHUB_REPOSITORY:?}"
theo="ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b  assets/joven_rubio/theo_alpha.glb"

nom=$(alth-python -c "import json,sys; print(json.load(open(sys.argv[1]))['nombre'])" "$carpeta/receta.json")
img=$(alth-python -c "import json,sys; print(json.load(open(sys.argv[1]))['imagen'])" "$carpeta/resumen.json")
rama="publicar/${nom}-issue-${N}"

git fetch -q origin "$base"
git checkout -q -B "$rama" "origin/$base"
[ -n "$img_ref" ] && git checkout -q "$img_ref" -- "$img" 2>/dev/null || true
echo "$theo" | sha256sum -c --quiet -

set +e
alth-python tools/publicar.py "$carpeta" --issue "$N" > publicar.json 2> publicar_err.txt
code=$?
set -e
grep -v -E "INFO|CUEW|^Fra|Saved|Draco|MeshOpt" publicar_err.txt | tail -20 || true
if [ "$code" -ne 0 ]; then
  motivo=$(grep -E "NO SE PUBLICA|Error|error" publicar_err.txt | tail -3 || true)
  gh issue comment "$N" -R "$repo" --body "**No se publica.** ${motivo:-publicar.py salió con $code (ver la corrida).}

La auditoría visual y la verificación técnica deciden: sin PASS no hay PR. La evidencia queda en el artifact de la corrida." || true
  git checkout -q -- . 2>/dev/null || true
  exit "$code"
fi
echo "$theo" | sha256sum -c --quiet -

git add "assets/$nom" data/medidas.csv kb
git add "$img" 2>/dev/null || true
git commit -q -m "publica $nom (auditoría visual PASS, issue #$N)"
git push -q -f origin "$rama"

cuerpo=$(alth-python - "$carpeta" "$N" <<'PY'
import json, sys
from pathlib import Path
carpeta, n = Path(sys.argv[1]), sys.argv[2]
r = json.loads(Path("publicar.json").read_text(encoding="utf-8"))
a = r.get("auditoria", {})
print(f"Publicación de `{r['asset']}` desde el issue #{n}.\n")
print(f"- auditoría visual: **{a.get('decision')}** (vista {a.get('vista')}; supera al aprobado anterior: {a.get('supera_aprobado')})")
print(f"- dimensiones (mm): {r.get('dimensiones_mm')}")
print(f"- capacidades aprendidas: {', '.join(r.get('capacidades_aprendidas') or []) or 'ninguna'}")
print(f"\nEvidencia: `{r['asset']}/auditoria.json` y `{r['asset']}/auditoria_comparacion.png`.")
print("\nFusionar este PR es el release del asset. Cerrarlo sin fusionar lo descarta.")
PY
)
if url=$(gh pr create -R "$repo" --base "$base" --head "$rama" --title "Publica $nom (issue #$N)" --body "$cuerpo" 2>pr_err.txt); then
  gh issue comment "$N" -R "$repo" --body "Auditoría visual **PASS**. PR de publicación: $url — fusiónalo para que entre a \`$base\`."
else
  if url=$(gh pr view "$rama" -R "$repo" --json url -q .url 2>/dev/null); then
    gh issue comment "$N" -R "$repo" --body "Auditoría visual **PASS**. PR actualizado: $url"
  else
    cmp="https://github.com/$repo/compare/$base...$rama?expand=1"
    gh issue comment "$N" -R "$repo" --body "Auditoría visual **PASS**. La rama \`$rama\` está lista; este repo no deja que Actions abra PRs, así que ábrelo con un clic: $cmp

(Para que se abra solo: Settings → Actions → General → *Allow GitHub Actions to create and approve pull requests*.)"
  fi
fi
echo "publicado en la rama $rama"
