"""
Fixtures Determinísticas de Mercado para a Auditoria de Referência (02/10/2026).
Garante que nenhum teste financeiro dependa de cotações voláteis ou chamadas de rede da internet.
"""

from typing import Dict, Any

# Câmbio PTAX de Auditoria
AUDIT_FX_AUDIT_SCENARIO = 5.2238   # Cenário conservador da auditoria de 02/10/2026
AUDIT_FX_REFERENCE = 5.4850        # Taxa de referência do benchmark local

# Futuros CBOT (¢/bushel)
AUDIT_CBOT_SOJA_CENTS = 1185.25
AUDIT_CBOT_MILHO_CENTS = 435.50

# Prêmios de Exportação FOB (¢/bushel)
AUDIT_PORT_PREMIUMS_CENTS = {
    "STS": {"SOJA": 90.00, "MILHO": 60.00},
    "PNG": {"SOJA": 85.00, "MILHO": 55.00},
    "BCR": {"SOJA": 80.00, "MILHO": 55.00},
    "ITQ": {"SOJA": 82.00, "MILHO": 58.00},
    "RG":  {"SOJA": 75.00, "MILHO": 50.00},
}

# Custos Portuários de Referência
AUDIT_PORT_COSTS = {
    "STS": {
        "elevation_usd_ton": 8.00,
        "other_port_costs_brl_ton": 15.00,
        "demurrage_risk_usd_ton": 2.50,
        "waiting_days": 28,
    },
    "BCR": {
        "elevation_usd_ton": 8.50,
        "other_port_costs_brl_ton": 14.00,
        "demurrage_risk_usd_ton": 0.80,
        "waiting_days": 10,
    },
    "PNG": {
        "elevation_usd_ton": 7.50,
        "other_port_costs_brl_ton": 12.00,
        "demurrage_risk_usd_ton": 2.00,
        "waiting_days": 24,
    },
}

# Tabela Oficial de Fundos Tributários Estaduais Incidentes (R$/saca)
AUDIT_STATE_TAX_FUNDS = {
    "MT": {"SOJA": 2.85, "MILHO": 1.45, "tributo": "FETHAB"},
    "GO": {"SOJA": 1.65, "MILHO": 0.90, "tributo": "FUNDEINFRA"},
    "BA": {"SOJA": 0.60, "MILHO": 0.35, "tributo": "PRODEAGRO"},
    "PR": {"SOJA": 0.00, "MILHO": 0.00, "tributo": "Isento (Lei Kandir)"},
    "RS": {"SOJA": 0.00, "MILHO": 0.00, "tributo": "Isento (Lei Kandir)"},
}

# Tabela de Fretes Rodoviários (R$/tonelada)
AUDIT_FREIGHT_RATES_TON = {
    ("sorriso_mt", "STS"): 420.00,
    ("sorriso_mt", "PNG"): 440.00,
    ("sorriso_mt", "BCR"): 360.00,
    ("rondonopolis_mt", "STS"): 310.00,
    ("rio_verde_go", "STS"): 240.00,
    ("cascavel_pr", "PNG"): 145.00,
    ("passo_fundo_rs", "RG"): 130.00,
    ("lem_ba", "ITQ"): 290.00,
}

# Preços Médios de Balcão Físico no Interior (R$/saca)
AUDIT_CASH_PRICES_BRL_BAG = {
    "sorriso_mt": {"SOJA": 122.50, "MILHO": 48.00},
    "rondonopolis_mt": {"SOJA": 127.00, "MILHO": 52.50},
    "rio_verde_go": {"SOJA": 128.50, "MILHO": 54.00},
    "cascavel_pr": {"SOJA": 133.00, "MILHO": 58.00},
    "passo_fundo_rs": {"SOJA": 134.50, "MILHO": 60.00},
    "lem_ba": {"SOJA": 125.00, "MILHO": 50.00},
}

# Índices Macroeconômicos Oficiais (BACEN SGS)
AUDIT_MACRO_INDICES = {
    "CDI_ANNUAL": {"value": 13.65, "unit": "% a.a.", "ref_date": "02/10/2026"},
    "SELIC_META": {"value": 13.75, "unit": "% a.a.", "ref_date": "02/10/2026"},
    "IPCA_12M":   {"value": 4.42,  "unit": "%",      "ref_date": "08/2026"},
    "IGPM_12M":   {"value": 6.52,  "unit": "%",      "ref_date": "09/2026"},
}
