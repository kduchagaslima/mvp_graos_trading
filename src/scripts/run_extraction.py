"""
Script de linha de comando para execução pontual ou agendada da extração de Market Data.
Uso: python -m src.scripts.run_extraction
"""

import sys
import json
from src.services.extractor import extract_and_persist_market_data


def main():
    print("🌾 Iniciando Extração e Persistência de Market Data de Grãos...")
    try:
        summary = extract_and_persist_market_data()
        print("\n✅ Extração concluída com sucesso!")
        print(f"• Data de Referência: {summary['quote_date']}")
        print(f"• Total de registros extraídos: {summary['total_extracted']}")
        print(f"• Total de registros persistidos/atualizados: {summary['total_persisted']}")
        print("• Detalhamento por categoria:")
        for cat, count in summary["breakdown"].items():
            print(f"  - {cat}: {count} cotações")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro durante a extração: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
