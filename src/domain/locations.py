"""
Definições de praças de originação, portos de escoamento e custos logísticos de referência.
"""

from pydantic import BaseModel
from typing import Dict, List, Optional, Any


class Port(BaseModel):
    id: str
    name: str
    state: str
    elevation_cost_usd_ton: float  # Custo de elevação (THC / Terminal Handling) em USD/ton
    other_port_costs_brl_ton: float  # Amostragem, classificação, despacho em R$/ton
    typical_waiting_days: int = 15  # Tempo médio de espera de navio em dias (pico de safra)
    demurrage_risk_usd_ton: float = 1.50  # Provisão típica de demurrage por tonelada em USD/ton
    main_terminals: List[str] = []


class OriginationHub(BaseModel):
    id: str
    name: str
    state: str
    default_port_id: str
    freight_to_port_brl_ton: Dict[str, float]  # {port_id: frete_brl_ton}
    state_tax_fund_brl_bag: Dict[str, float]  # {COMMODITY: valor_r$_por_saca} (ex: FETHAB MT, FUNDEINFRA GO)
    typical_cash_basis_discount_brl_bag: float = 0.0  # Desconto histórico de balcão vs FOB líquido


PORTS: Dict[str, Port] = {
    "STS": Port(
        id="STS",
        name="Porto de Santos",
        state="SP",
        elevation_cost_usd_ton=8.00,
        other_port_costs_brl_ton=15.00,
        typical_waiting_days=28,
        demurrage_risk_usd_ton=2.50,
        main_terminals=["CLI / Rumo", "T-139 Cargill", "ADM Ponta da Praia", "Tiplam VLI", "Cutrale"],
    ),
    "PNG": Port(
        id="PNG",
        name="Porto de Paranaguá",
        state="PR",
        elevation_cost_usd_ton=7.50,
        other_port_costs_brl_ton=12.00,
        typical_waiting_days=24,
        demurrage_risk_usd_ton=2.00,
        main_terminals=["Corredor Público (APPA)", "Cotriguaçu", "Bunge", "Cargill"],
    ),
    "BCR": Port(
        id="BCR",
        name="Porto de Barcarena",
        state="PA",
        elevation_cost_usd_ton=8.50,
        other_port_costs_brl_ton=14.00,
        typical_waiting_days=10,
        demurrage_risk_usd_ton=0.80,
        main_terminals=["Terfron (Bunge/Amaggi)", "Ponta da Montanha (Hidrovias)"],
    ),
    "ITQ": Port(
        id="ITQ",
        name="Porto do Itaqui",
        state="MA",
        elevation_cost_usd_ton=8.00,
        other_port_costs_brl_ton=12.00,
        typical_waiting_days=14,
        demurrage_risk_usd_ton=1.20,
        main_terminals=["Tegram (Consórcio)", "Viterra", "NovaAgri"],
    ),
    "RG": Port(
        id="RG",
        name="Porto de Rio Grande",
        state="RS",
        elevation_cost_usd_ton=7.00,
        other_port_costs_brl_ton=10.00,
        typical_waiting_days=12,
        demurrage_risk_usd_ton=1.00,
        main_terminals=["Termasa", "Tergrasa", "Bunge"],
    ),
}

ORIGINATION_HUBS: Dict[str, OriginationHub] = {
    "sorriso_mt": OriginationHub(
        id="sorriso_mt",
        name="Sorriso - MT",
        state="MT",
        default_port_id="STS",
        freight_to_port_brl_ton={
            "STS": 420.00,
            "PNG": 440.00,
            "BCR": 360.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 2.85,  # FETHAB MT Soja
            "MILHO": 1.45,  # FETHAB MT Milho
        },
        typical_cash_basis_discount_brl_bag=5.00,
    ),
    "rondonopolis_mt": OriginationHub(
        id="rondonopolis_mt",
        name="Rondonópolis - MT",
        state="MT",
        default_port_id="STS",
        freight_to_port_brl_ton={
            "STS": 310.00,
            "PNG": 325.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 2.85,
            "MILHO": 1.45,
        },
        typical_cash_basis_discount_brl_bag=4.00,
    ),
    "rio_verde_go": OriginationHub(
        id="rio_verde_go",
        name="Rio Verde - GO",
        state="GO",
        default_port_id="STS",
        freight_to_port_brl_ton={
            "STS": 240.00,
            "PNG": 270.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 1.65,  # FUNDEINFRA GO Soja
            "MILHO": 0.90,  # FUNDEINFRA GO Milho
        },
        typical_cash_basis_discount_brl_bag=3.50,
    ),
    "cascavel_pr": OriginationHub(
        id="cascavel_pr",
        name="Cascavel - PR",
        state="PR",
        default_port_id="PNG",
        freight_to_port_brl_ton={
            "PNG": 145.00,
            "STS": 220.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 0.00,
            "MILHO": 0.00,
        },
        typical_cash_basis_discount_brl_bag=2.00,
    ),
    "passo_fundo_rs": OriginationHub(
        id="passo_fundo_rs",
        name="Passo Fundo - RS",
        state="RS",
        default_port_id="RG",
        freight_to_port_brl_ton={
            "RG": 130.00,
            "PNG": 190.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 0.00,
            "MILHO": 0.00,
        },
        typical_cash_basis_discount_brl_bag=2.00,
    ),
    "lem_ba": OriginationHub(
        id="lem_ba",
        name="Luís Eduardo Magalhães - BA",
        state="BA",
        default_port_id="ITQ",
        freight_to_port_brl_ton={
            "ITQ": 290.00,
            "STS": 340.00,
        },
        state_tax_fund_brl_bag={
            "SOJA": 0.60,
            "MILHO": 0.35,
        },
        typical_cash_basis_discount_brl_bag=3.00,
    ),
}


# Tabela Oficial de Fundos Tributários Estaduais Incidentes
STATE_TAX_FUNDS: List[Dict[str, Any]] = [
    {
        "state": "Mato Grosso (MT)",
        "uf": "MT",
        "tributo": "FETHAB",
        "full_name": "Fundo Estadual de Transporte e Habitação",
        "soja_brl_bag": 2.85,
        "milho_brl_bag": 1.45,
        "legal_basis": "Lei Estadual nº 7.263/2000 (Art. 7º)",
        "finalidade": "Manutenção, conservação e pavimentação de rodovias estaduais e obras estruturantes.",
        "regime": "Retenção na fonte pelo adquirente ou recolhimento antecipado nas operações interestaduais/porto.",
    },
    {
        "state": "Goiás (GO)",
        "uf": "GO",
        "tributo": "FUNDEINFRA",
        "full_name": "Fundo Estadual de Infraestrutura",
        "soja_brl_bag": 1.65,
        "milho_brl_bag": 0.90,
        "legal_basis": "Lei Estadual nº 21.670/2022",
        "finalidade": "Financiamento de obras de infraestrutura viária e modernização do escoamento agrícola em GO.",
        "regime": "Condição para manutenção de incentivos fiscais e escoamento interestadual/porto.",
    },
    {
        "state": "Bahia (BA)",
        "uf": "BA",
        "tributo": "PRODEAGRO",
        "full_name": "Programa de Desenvolvimento da Agropecuária",
        "soja_brl_bag": 0.60,
        "milho_brl_bag": 0.35,
        "legal_basis": "Lei Estadual nº 13.208/2014",
        "finalidade": "Fundo de desenvolvimento agropecuário, pesquisa e defesa sanitária vegetal no MATOPIBA.",
        "regime": "Contribuição facultativa vinculada a benefícios fiscais operacionais da trading.",
    },
    {
        "state": "Paraná (PR)",
        "uf": "PR",
        "tributo": "Isento",
        "full_name": "Imunidade Constitucional (Lei Kandir)",
        "soja_brl_bag": 0.00,
        "milho_brl_bag": 0.00,
        "legal_basis": "Lei Complementar nº 87/1996 (Lei Kandir)",
        "finalidade": "Imunidade total de ICMS e sem exigência de fundos agropecuários no escoamento via Paranaguá (PNG).",
        "regime": "Não incidência direta para exportação e originação paranaense.",
    },
    {
        "state": "Rio Grande do Sul (RS)",
        "uf": "RS",
        "tributo": "Isento",
        "full_name": "Imunidade Constitucional (Lei Kandir)",
        "soja_brl_bag": 0.00,
        "milho_brl_bag": 0.00,
        "legal_basis": "Lei Complementar nº 87/1996 (Lei Kandir)",
        "finalidade": "Imunidade de ICMS e ausência de retenções de fundos estaduais no escoamento via Rio Grande (RG).",
        "regime": "Isenção total no escoamento para porto gaúcho.",
    },
]

