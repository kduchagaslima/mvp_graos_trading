#!/usr/bin/env bash
set -e

# Script de empacotamento da AWS Lambda com dependências Python 3.11 ARM64
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

echo "2. Instalando dependências de produção para Python 3.11 (Linux arm64)..."
if command -v pip3 &> /dev/null; then
    pip3 install \
        --platform manylinux2014_aarch64 \
        --target "$PACKAGE_DIR" \
        --implementation cp \
        --python-version 3.11 \
        --only-binary=:all: \
        --upgrade \
        -r "$REPO_ROOT/requirements.txt" || {
            echo "Aviso: Instalação com --platform falhou, tentando instalação padrão com pip..."
            pip3 install -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements.txt"
        }
elif command -v pip &> /dev/null; then
    pip install -t "$PACKAGE_DIR" -r "$REPO_ROOT/requirements.txt"
fi

# Remove arquivos desnecessários para reduzir o tamanho do pacote
echo "3. Otimizando tamanho do pacote (removendo testes, caches e doc)..."
find "$PACKAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

echo "4. Gerando arquivo compactado: $OUTPUT_ZIP..."
(cd "$PACKAGE_DIR" && zip -q -r "$OUTPUT_ZIP" .)

echo "✅ Empacotamento concluído com sucesso: $OUTPUT_ZIP"
ls -lh "$OUTPUT_ZIP"
