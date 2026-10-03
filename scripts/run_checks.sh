#!/usr/bin/env bash
set -e

# ==============================================================================
# AgriTrading — Script de Verificação Contínua e Integridade Local (CI / QA)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

echo "=========================================================="
echo "🌾 AgriTrading — Executando Bateria de Verificações Locais"
echo "=========================================================="

# 1. Auditoria de Rastreabilidade
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "UNKNOWN")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "UNKNOWN")
echo "📍 Git Commit: $GIT_SHA (Branch: $BRANCH)"
echo "📍 Data/Hora: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# 2. Verificação de Sintaxe Python
echo ""
echo "🔍 1/3 Verificando sintaxe dos módulos Python..."
python3 -c "
import ast, glob, sys
files = glob.glob('src/**/*.py', recursive=True) + glob.glob('tests/**/*.py', recursive=True)
for f in files:
    with open(f, 'r', encoding='utf-8') as fh:
        ast.parse(fh.read(), filename=f)
print(f'✅ Sintaxe Python validada sem erros em {len(files)} arquivos.')
"

# 3. Execução da Suíte Completa de Testes
echo ""
echo "🧪 2/3 Executando suíte completa de testes automatizados com pytest..."
if command -v /home/celima/.local/bin/uv &> /dev/null; then
    /home/celima/.local/bin/uv run \
        --with pytest \
        --with pydantic \
        --with requests \
        --with sqlalchemy \
        --with fastapi \
        --with httpx \
        pytest -o cache_dir=/tmp/.pytest_cache -v tests/
else
    pytest -o cache_dir=/tmp/.pytest_cache -v tests/
fi
echo "✅ Todos os testes automatizados passaram com sucesso."

# 4. Checagem de integridade de dependências
echo ""
echo "📦 3/3 Validando presença de arquivos críticos de configuração..."
test -f requirements.txt && echo "  ✓ requirements.txt presente"
test -f requirements-lambda.txt && echo "  ✓ requirements-lambda.txt presente"
test -f pytest.ini && echo "  ✓ pytest.ini presente"
test -f docs/AUDIT_FINANCIAL_BASELINE.md && echo "  ✓ AUDIT_FINANCIAL_BASELINE.md presente"
test -f tests/test_api_contracts_inventory.py && echo "  ✓ Inventário de endpoints presente"

echo ""
echo "=========================================================="
echo "🎉 Sucesso! Todas as verificações de baseline foram aprovadas."
echo "=========================================================="
