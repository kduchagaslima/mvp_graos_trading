#!/usr/bin/env bash
set -e

# Script de empacotamento da AWS Lambda com dependências Python 3.11
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$TERRAFORM_DIR")"

BUILD_DIR="$TERRAFORM_DIR/build"
PACKAGE_DIR="$BUILD_DIR/package"
OUTPUT_ZIP="$BUILD_DIR/lambda_function.zip"

echo "=========================================================="
echo "📦 Empacotando Lambda Serverless para AgriTrading"
echo "=========================================================="

rm -rf "$PACKAGE_DIR" "$OUTPUT_ZIP"
mkdir -p "$PACKAGE_DIR"

echo "1. Copiando código fonte da aplicação (src/)..."
cp -r "$REPO_ROOT/src" "$PACKAGE_DIR/src"

echo "2. Instalando dependências de produção para Python 3.11..."
INSTALLED=false
if [ "${USE_DOCKER_BUILD:-false}" = "true" ] && command -v docker &> /dev/null; then
    echo "Usando Docker (AWS SAM build-python3.11 / Amazon Linux 2)..."
    if docker run --rm \
        -v "$REPO_ROOT/requirements-lambda.txt:/requirements.txt:ro" \
        -v "$PACKAGE_DIR:/package" \
        public.ecr.aws/sam/build-python3.11:latest \
        bash -c "pip install --no-cache-dir --upgrade -t /package -r /requirements.txt && chown -R $(id -u):$(id -g) /package"; then
        INSTALLED=true
    else
        echo "Aviso: Build via Docker falhou, chaveando para pip local..."
    fi
fi

if [ "$INSTALLED" = "false" ]; then
    if command -v pip3 &> /dev/null; then
        pip3 install --no-cache-dir -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements-lambda.txt"
    elif command -v pip &> /dev/null; then
        pip install --no-cache-dir -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements-lambda.txt"
    elif command -v python3 &> /dev/null; then
        python3 -m pip install --no-cache-dir -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements-lambda.txt"
    fi
fi

echo "3. Otimizando tamanho do pacote (removendo apenas caches desnecessários)..."
find "$PACKAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true

echo "4. Gerando arquivo compactado: $OUTPUT_ZIP..."
if command -v zip &> /dev/null; then
    (cd "$PACKAGE_DIR" && zip -q -r "$OUTPUT_ZIP" .)
else
    python3 -c "import zipfile, os; z = zipfile.ZipFile('$OUTPUT_ZIP', 'w', zipfile.ZIP_DEFLATED); [z.write(os.path.join(r, f), os.path.relpath(os.path.join(r, f), '$PACKAGE_DIR')) for r, d, fs in os.walk('$PACKAGE_DIR') for f in fs]"
fi

echo "✅ Empacotamento concluído com sucesso: $OUTPUT_ZIP"
ls -lh "$OUTPUT_ZIP"
