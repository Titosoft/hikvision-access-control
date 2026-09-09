#!/usr/bin/env bash
# Prepare and publish a HACS release from the committed main branch.
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Uso: ./bump_version.sh [patch|minor|major|X.Y.Z] [--dry-run]

Sem argumento, incrementa o patch. Exemplo: 0.1.4 -> 0.1.5.
--dry-run mostra a versão e as notas, sem alterar arquivos ou publicar.

Antes de publicar, faça commit das mudanças e preencha [Unreleased] no
CHANGELOG.md. Requer git, GitHub CLI autenticado (gh auth login) e Python 3.12+.
As dependências de teste são instaladas automaticamente quando necessário.
Use PYTHON=/caminho/python para escolher o interpretador; por padrão usa
.venv/bin/python ou python3.
EOF
}

fail() { printf 'Erro: %s\n' "$*" >&2; exit 1; }

bump=patch
bump_set=false
dry_run=false
for argument in "$@"; do
  case "$argument" in
    --help|-h) usage; exit 0 ;;
    --dry-run) dry_run=true ;;
    -*) fail "Opção desconhecida: $argument" ;;
    *)
      if "$bump_set"; then fail "Informe apenas uma versão ou incremento."; fi
      bump=$argument
      bump_set=true
      ;;
  esac
done

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
manifest=custom_components/hikvision_access_control/manifest.json
if [[ -n ${PYTHON:-} ]]; then
  python_bin=$PYTHON
elif [[ -x .venv/bin/python ]]; then
  python_bin=$PWD/.venv/bin/python
else
  python_bin=python3
fi
command -v "$python_bin" >/dev/null || fail "Python não encontrado: $python_bin"
"$python_bin" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' || \
  fail "Use Python 3.12 ou superior: $python_bin"
release_tmp=$(mktemp -d "${TMPDIR:-/tmp}/hikvision-release.XXXXXX")
trap 'rm -rf -- "$release_tmp"' EXIT
release_phase=preparação
trap 'printf "Falha na etapa: %s. Execução interrompida; confira git status antes de continuar.\n" "$release_phase" >&2' ERR

"$python_bin" - "$manifest" "$bump" "$release_tmp" <<'PY'
import datetime
import json
from pathlib import Path
import re
import sys

manifest_path, bump, output = sys.argv[1:]
destination = Path(output)
manifest = json.loads(Path(manifest_path).read_text())
pattern = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
current = manifest["version"]
if not re.fullmatch(pattern, current):
    sys.exit(f"Versão atual inválida: {current}. Esperado X.Y.Z.")
parts = list(map(int, current.split(".")))
if bump in ("major", "minor", "patch"):
    index = ("major", "minor", "patch").index(bump)
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    version = ".".join(map(str, parts))
elif re.fullmatch(pattern, bump):
    version = bump
else:
    sys.exit("Use patch, minor, major ou uma versão X.Y.Z (sem prefixo v).")
if tuple(map(int, version.split("."))) <= tuple(map(int, current.split("."))):
    sys.exit(f"A nova versão precisa ser maior que {current}.")

changelog = Path("CHANGELOG.md").read_text()
heading = re.search(r"^## \[Unreleased\][ \t]*$", changelog, re.MULTILINE)
if not heading:
    sys.exit("Inclua uma seção ## [Unreleased] com as mudanças no CHANGELOG.md.")
tail = changelog[heading.end():]
next_heading = re.search(r"^## ", tail, re.MULTILINE)
notes = tail[:next_heading.start() if next_heading else len(tail)].strip()
if not any(line.strip() and not line.lstrip().startswith("#") for line in notes.splitlines()):
    sys.exit("Preencha as notas de [Unreleased] antes de publicar.")
if re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE):
    sys.exit(f"O changelog já contém a versão {version}.")
dated_heading = f"## [Unreleased]\n\n## [{version}] - {datetime.date.today().isoformat()}"
changelog = changelog[:heading.start()] + dated_heading + changelog[heading.end():]
manifest["version"] = version
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(destination / "CHANGELOG.md").write_text(changelog)
(destination / "notes.md").write_text(notes + "\n")
(destination / "versions").write_text(f"{current} {version}\n")
PY

read -r current_version new_version < "$release_tmp/versions"
tag="v$new_version"
printf 'Versão: %s -> %s\nTag: %s\n\nNotas da release:\n' "$current_version" "$new_version" "$tag"
cat "$release_tmp/notes.md"
if "$dry_run"; then
  printf '\nSimulação: atualizar manifest/changelog, validar, commitar, enviar main e tag, publicar no GitHub.\n'
  exit 0
fi

release_phase=pré-verificações
command -v git >/dev/null || fail "Instale o git."
command -v gh >/dev/null || fail "Instale o GitHub CLI e execute gh auth login."
[[ $(git branch --show-current) == main ]] || fail "Execute na branch main."
[[ -z $(git status --porcelain) ]] || fail "Faça commit das alterações pendentes antes de publicar."
origin_url=$(git remote get-url origin)
gh auth status
release_repo=$(gh repo view "$origin_url" --json nameWithOwner --jq .nameWithOwner)
if ! "$python_bin" -c 'import pytest, requests, ruff' 2>/dev/null; then
  release_phase=instalação-das-dependências
  printf 'Instalando dependências de teste em %s...\n' "$python_bin"
  if command -v uv >/dev/null; then
    uv pip install --python "$python_bin" -r requirements-test.txt
  elif "$python_bin" -m pip --version >/dev/null 2>&1; then
    "$python_bin" -m pip install -r requirements-test.txt
  elif "$python_bin" -m ensurepip --upgrade >/dev/null 2>&1; then
    "$python_bin" -m pip install -r requirements-test.txt
  elif command -v pip3 >/dev/null && pip3 help 2>/dev/null | grep -q -- '--python'; then
    pip3 --python "$python_bin" install -r requirements-test.txt
  else
    fail "Não foi possível instalar no ambiente. Instale uv ou recrie-o com: python3.12 -m venv .venv"
  fi
  "$python_bin" -c 'import pytest, requests, ruff' || \
    fail "Não foi possível instalar as dependências de teste."
fi
git fetch origin main --tags
git merge-base --is-ancestor refs/remotes/origin/main HEAD || fail "A main local está atrasada ou divergiu de origin/main. Sincronize-a antes de publicar."
if git show-ref --verify --quiet "refs/tags/$tag"; then
  fail "A tag $tag já existe. Escolha outra versão."
fi

release_phase=validação
"$python_bin" - <<'PY'
import json
from pathlib import Path

for path in [Path("hacs.json"), *Path("custom_components").rglob("*.json")]:
    json.loads(path.read_text())
PY
"$python_bin" -m compileall -q custom_components tests
"$python_bin" -m ruff check custom_components tests
"$python_bin" -m pytest
git diff --check
[[ -z $(git status --porcelain) ]] || fail "As verificações alteraram arquivos; confira git status."

release_phase=commit
cp "$release_tmp/manifest.json" "$manifest"
cp "$release_tmp/CHANGELOG.md" CHANGELOG.md
git add -- "$manifest" CHANGELOG.md
git commit -m "Release $tag"
git tag -a "$tag" -m "Release $tag"

release_phase=push
if ! git push --atomic origin HEAD:refs/heads/main "refs/tags/$tag"; then
  printf '\nO commit e a tag foram criados localmente, mas o push falhou.\n' >&2
  printf 'Corrija o erro e envie a mesma versão, sem executar outro bump:\n' >&2
  printf 'git push --atomic origin HEAD:refs/heads/main refs/tags/%q\n' "$tag" >&2
  printf 'Depois publique a release:\n' >&2
  printf 'gh release create %q --repo %q --verify-tag --title %q --generate-notes\n' "$tag" "$release_repo" "$tag" >&2
  exit 1
fi

release_phase=publicação
if ! gh release create "$tag" --repo "$release_repo" --verify-tag \
  --title "$tag" --notes-file "$release_tmp/notes.md"; then
  printf '\nA main e a tag já foram enviadas. Confira se a release foi criada:\n' >&2
  printf 'gh release view %q --repo %q\n' "$tag" "$release_repo" >&2
  printf 'Se ela não existir, publique a mesma tag sem executar o bump novamente:\n' >&2
  printf 'gh release create %q --repo %q --verify-tag --title %q --generate-notes\n' "$tag" "$release_repo" "$tag" >&2
  exit 1
fi
printf '\nRelease %s publicada.\n' "$tag"
