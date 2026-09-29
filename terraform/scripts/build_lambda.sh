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
if command -v docker &> /dev/null; then
    echo "Usando Docker para garantir binários 100% compatíveis com AWS Lambda..."
    docker run --rm \
        -v "$REPO_ROOT/requirements-lambda.txt:/requirements.txt:ro" \
        -v "$PACKAGE_DIR:/package" \
        python:3.11-slim \
        pip install --no-cache-dir --upgrade -t /package -r /requirements.txt
elif command -v pip3 &> /dev/null; then
    pip3 install -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements-lambda.txt"
elif command -v pip &> /dev/null; then
    pip install -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements-lambda.txt"
fi

echo "3. Otimizando tamanho do pacote (removendo testes, caches e doc)..."
find "$PACKAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

echo "4. Gerando arquivo compactado: $OUTPUT_ZIP..."
(cd "$PACKAGE_DIR" && zip -q -r "$OUTPUT_ZIP" .)

echo "✅ Empacotamento concluído com sucesso: $OUTPUT_ZIP"
ls -lh "$OUTPUT_ZIP"
