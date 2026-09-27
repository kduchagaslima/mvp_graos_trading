"""
Dashboard Interativo do MVP de Market Data e Trading de Grãos.
Interface profissional com alto contraste, tipografia nítida e visualização clara
para mesas de trading, paridade de exportação, custo de carrego e análise de risco.
"""

import sys
from pathlib import Path

# Garante que a raiz da aplicação (/app ou repo root) esteja no sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from src.domain.commodities import CommodityType, COMMODITY_SPECS, get_commodity_specs
from src.domain.locations import ORIGINATION_HUBS, PORTS
from src.domain.models import (
    ParityCalculationInput,
    CarryCalculationInput,
    ScenarioSimulationInput,
)
from src.engines.export_parity import ExportParityEngine
from src.engines.carry_cost import CarryCostEngine
from src.engines.stress_tester import StressTesterEngine
from src.services.market_data import market_service
from src.db.connection import SessionLocal
from src.db.repository import MarketDataRepository
from src.db.models import ExtractionLog

# Configuração da Página
st.set_page_config(
    page_title="AgriTrading Market Data & Paridade",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização CSS de Alto Contraste e Legibilidade
st.markdown(
    """
    <style>
    /* Estilos globais para alto contraste e legibilidade */
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
    }
    
    /* Cards de Métricas com borda nítida e texto escuro */
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 16px 20px !important;
        border-radius: 10px !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06) !important;
    }
    [data-testid="stMetricLabel"] {
        color: #475569 !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
    }
    [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-size: 1.65rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    
    /* Abas com destaque visual claro */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f1f5f9;
        padding: 6px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #475569;
        font-weight: 600;
        padding: 8px 16px;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #16a34a !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08) !important;
    }

    /* Container de cartões personalizados */
    .highlight-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar - Painel de Cotações e Parâmetros
st.sidebar.title("🌾 Mesa de Market Data")
st.sidebar.caption("Parâmetros Globais de Negociação")

# Seleção da Commodity
selected_commodity_str = st.sidebar.selectbox(
    "Commodity em Negociação",
    options=["SOJA", "MILHO"],
    index=0,
    help="Define fatores de conversão (bushel/ton/saca) e cotações de bolsa.",
)
selected_commodity = CommodityType(selected_commodity_str)
specs = get_commodity_specs(selected_commodity)

# Cotação CBOT
default_cbot = market_service.get_cbot_price(selected_commodity.value)
cbot_price = st.sidebar.number_input(
    f"Chicago CBOT {specs.name} (cents/bu)",
    min_value=200.0,
    max_value=3000.0,
    value=default_cbot,
    step=2.5,
    help=f"Cotação futura em Chicago ({specs.ticker_cbot})",
)

# Câmbio USD/BRL
current_fx = market_service.get_fx_usd_brl()
col_fx1, col_fx2 = st.sidebar.columns([3, 1])
with col_fx1:
    usd_brl = st.number_input(
        "Dólar PTAX (USD/BRL)",
        min_value=3.0,
        max_value=10.0,
        value=current_fx,
        step=0.01,
        format="%.4f",
    )
with col_fx2:
    st.write("")
    if st.button("🔄 BCB", help="Consultar taxa oficial PTAX online do Banco Central"):
        live_fx = market_service.fetch_live_usd_brl()
        st.sidebar.success(f"BCB: {live_fx:.4f}")
        usd_brl = live_fx

# Porto de Embarque
port_keys = list(PORTS.keys())
selected_port_id = st.sidebar.selectbox(
    "Porto de Embarque",
    options=port_keys,
    index=1 if "STS" in port_keys else 0,
    format_func=lambda x: f"{PORTS[x].name} ({x})",
)
port_info = PORTS[selected_port_id]

# Prêmio FOB no Porto
default_premium = market_service.get_port_premium(selected_port_id, selected_commodity.value)
port_premium = st.sidebar.number_input(
    f"Prêmio FOB {selected_port_id} (cents/bu)",
    min_value=-200.0,
    max_value=400.0,
    value=default_premium,
    step=1.0,
    help="Prêmio de exportação sobre o contrato de Chicago",
)

# Praça de Originação no Interior
hub_keys = list(ORIGINATION_HUBS.keys())
selected_hub_id = st.sidebar.selectbox(
    "Praça de Originação (Interior)",
    options=hub_keys,
    index=0,
    format_func=lambda x: ORIGINATION_HUBS[x].name,
)
hub_info = ORIGINATION_HUBS[selected_hub_id]

# Preço Físico Praticado no Balcão
default_cash = market_service.get_cash_price(selected_hub_id, selected_commodity.value) or 120.0
cash_price = st.sidebar.number_input(
    f"Preço Balcão Atual ({hub_info.name}) (R$/saca)",
    min_value=20.0,
    max_value=300.0,
    value=default_cash,
    step=0.50,
    help="Preço à vista ofertado/praticado no mercado físico da região",
)

# Ingestão e Persistência no Banco de Dados
st.sidebar.markdown("---")
st.sidebar.subheader("🗄️ Base de Dados & ETL")
if st.sidebar.button("⚡ Extrair & Persistir Market Data", use_container_width=True, help="Coleta cotações do BCB PTAX, CBOT, Prêmios e Físico e grava no PostgreSQL"):
    with st.spinner("Extraindo e persistindo dados no banco..."):
        try:
            from src.services.extractor import extract_and_persist_market_data
            summary = extract_and_persist_market_data()
            st.sidebar.success(f"✅ {summary['total_persisted']} cotações gravadas!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erro na extração: {e}")

# Cabeçalho Principal com Tipografia Nítida
st.title("🌾 AgriTrading - Market Data & Motor de Projeções")
st.markdown(
    f"<p style='color: #475569; font-size: 1.05rem; margin-top: -10px; margin-bottom: 20px;'>"
    f"Formação de preço de exportação (FOB/FAS), custo de carrego e análise de risco para grãos "
    f"| <b>{datetime.now().strftime('%d/%m/%Y %H:%M')}</b></p>",
    unsafe_allow_html=True,
)

# Top Bar com KPIs Globais Claros
kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
fob_cents_total = cbot_price + port_premium
fob_usd_ton_calc = fob_cents_total * specs.cents_per_bu_to_usd_per_ton
fob_brl_bag_calc = (fob_usd_ton_calc * usd_brl) * 0.06

with kpi_col1:
    st.metric(
        label=f"CBOT {selected_commodity.value}",
        value=f"{cbot_price:.2f} ¢/bu",
        delta=f"Prêmio: {port_premium:+.2f} ¢/bu",
    )
with kpi_col2:
    st.metric(
        label="Dólar PTAX (Spot)",
        value=f"R$ {usd_brl:.4f}",
        delta="Banco Central",
    )
with kpi_col3:
    st.metric(
        label=f"FOB {selected_port_id} (USD/ton)",
        value=f"$ {fob_usd_ton_calc:.2f}",
        delta=f"{fob_cents_total:.2f} ¢/bu total",
    )
with kpi_col4:
    st.metric(
        label="FOB Equivalente (R$/saca)",
        value=f"R$ {fob_brl_bag_calc:.2f}",
        delta="Bruto no Navio",
    )

st.markdown("<br>", unsafe_allow_html=True)

# Abas Principais do Sistema
tab_paridade, tab_forward, tab_stress, tab_tabelas, tab_database = st.tabs([
    "📊 Calculadora de Paridade de Exportação",
    "📈 Curva Forward & Custo de Carrego",
    "⚡ Simulador de Cenários e Estresse",
    "📋 Custos Logísticos e Fiscais",
    "🗄️ Banco de Dados & Histórico",
])

# ==============================================================================
# TAB 1: CALCULADORA DE PARIDADE DE EXPORTAÇÃO
# ==============================================================================
with tab_paridade:
    st.subheader(f"Formação do Preço de Paridade de Exportação: {hub_info.name} ➔ {port_info.name}")
    st.markdown(
        f"<p style='color: #475569;'>Cálculo automatizado partindo da cotação internacional no porto "
        f"até o armazém no interior, deduzindo logística, impostos e margem comercial.</p>",
        unsafe_allow_html=True,
    )
    
    # Parâmetros Ajustáveis na Linha
    with st.expander("⚙️ Ajustar Custos Logísticos, Impostos e Margem Comercial", expanded=False):
        exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4)
        
        default_freight = hub_info.freight_to_port_brl_ton.get(selected_port_id, 350.0)
        with exp_col1:
            freight_ton = st.number_input("Frete Rodoviário (R$/ton)", value=default_freight, step=10.0)
            elevation_ton = st.number_input("Elevação Portuária (USD/ton)", value=port_info.elevation_cost_usd_ton, step=0.50)
            
        with exp_col2:
            other_port_ton = st.number_input("Outras Desp. Portuárias (R$/ton)", value=port_info.other_port_costs_brl_ton, step=1.0)
            state_tax_bag = st.number_input(
                f"Fundo Estadual ({hub_info.state}) (R$/saca)",
                value=hub_info.state_tax_fund_brl_bag.get(selected_commodity.value, 0.0),
                step=0.20,
            )
            
        with exp_col3:
            funrural_pct = st.number_input("Funrural (%)", value=1.5, step=0.1)
            shrinkage_pct = st.number_input("Quebra Técnica / Umidade (%)", value=0.3, step=0.05)
            
        with exp_col4:
            margin_usd_ton = st.number_input("Margem Trading Alvo (USD/ton)", value=2.0, step=0.5)

    # Executar Cálculo de Paridade
    parity_input = ParityCalculationInput(
        commodity=selected_commodity,
        cbot_price_cents=cbot_price,
        port_premium_cents=port_premium,
        usd_brl_fx=usd_brl,
        hub_id=selected_hub_id,
        port_id=selected_port_id,
        freight_brl_ton=freight_ton,
        elevation_usd_ton=elevation_ton,
        other_port_costs_brl_ton=other_port_ton,
        state_tax_fund_brl_bag=state_tax_bag,
        funrural_pct=funrural_pct,
        shrinkage_loss_pct=shrinkage_pct,
        brokerage_margin_usd_ton=margin_usd_ton,
        current_cash_price_brl_bag=cash_price,
    )
    
    result = ExportParityEngine.calculate(parity_input)
    bk = result.cost_breakdown

    # Exibição dos Resultados Chave com Métricas de Alto Contraste
    res_col1, res_col2, res_col3, res_col4 = st.columns(4)
    with res_col1:
        st.metric(
            label="Preço FOB Porto (Bruto)",
            value=f"R$ {result.fob_brl_bag:.2f} / sc",
            delta=f"${result.fob_usd_ton:.2f} / ton",
            help="Preço colocado no navio antes de fretes internos e custos de originação.",
        )
    with res_col2:
        st.metric(
            label="Preço FAS Porto (Líquido)",
            value=f"R$ {bk.fas_brl_bag:.2f} / sc",
            delta="Livre ao lado do navio",
            help="Preço entregue no porto após deduzir custos de elevação portuária e despacho.",
        )
    with res_col3:
        st.metric(
            label="Preço Paridade Balcão (Líquido)",
            value=f"R$ {result.net_parity_price_brl_bag:.2f} / sc",
            delta=f"R$ {result.net_parity_price_brl_ton:.2f} / ton",
            help="Preço justo de compra no armazém/fazenda no interior.",
        )
    with res_col4:
        if result.originator_spread_brl_bag is not None:
            spread_color = "normal" if result.originator_spread_brl_bag >= 0 else "inverse"
            st.metric(
                label="Spread de Originação (Basis)",
                value=f"R$ {result.originator_spread_brl_bag:+.2f} / sc",
                delta=f"{result.originator_margin_pct:+.2f}% vs Balcão Físico",
                delta_color=spread_color,
                help="Paridade Teórica menos o Balcão Físico Praticado. Positivo = Margem favorável à compra pela trading.",
            )

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Gráficos e Decomposição Waterfall com Alto Contraste
    g_col1, g_col2 = st.columns([3, 2])
    
    with g_col1:
        st.write("##### 📉 Decomposição de Custos (Waterfall: FOB Porto ➔ Balcão Interior)")
        waterfall_fig = go.Figure(go.Waterfall(
            name="Formação de Preço",
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "relative", "total"],
            x=[
                "FOB Porto",
                "Elevação Port.",
                "Taxas Port.",
                "Frete Rodoviário",
                "Fundo Estadual",
                "Quebra Técnica",
                "Funrural",
                "Margem Trading",
                "Paridade Balcão",
            ],
            textposition="auto",
            text=[
                f"R${bk.fob_gross_brl_bag:.2f}",
                f"-R${bk.elevation_brl_bag:.2f}",
                f"-R${bk.other_port_costs_brl_bag:.2f}",
                f"-R${bk.freight_brl_bag:.2f}",
                f"-R${bk.state_fund_brl_bag:.2f}",
                f"-R${bk.shrinkage_brl_bag:.2f}",
                f"-R${bk.funrural_brl_bag:.2f}",
                f"-R${bk.trading_margin_brl_bag:.2f}",
                f"R${bk.net_parity_brl_bag:.2f}",
            ],
            y=[
                bk.fob_gross_brl_bag,
                -bk.elevation_brl_bag,
                -bk.other_port_costs_brl_bag,
                -bk.freight_brl_bag,
                -bk.state_fund_brl_bag,
                -bk.shrinkage_brl_bag,
                -bk.funrural_brl_bag,
                -bk.trading_margin_brl_bag,
                0,
            ],
            connector={"line": {"color": "#64748b", "width": 1.5}},
            decreasing={"marker": {"color": "#dc2626"}},
            increasing={"marker": {"color": "#16a34a"}},
            totals={"marker": {"color": "#2563eb"}},
        ))
        waterfall_fig.update_layout(
            template="plotly_white",
            font=dict(color="#0f172a", size=11),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            margin=dict(l=20, r=20, t=30, b=40),
            height=390,
            yaxis=dict(title="R$ por saca de 60kg", gridcolor="#f1f5f9"),
            xaxis=dict(tickangle=-25),
        )
        st.plotly_chart(waterfall_fig, use_container_width=True)

    with g_col2:
        st.write("##### 📋 Tabela Discriminada de Deduções")
        summary_df = pd.DataFrame({
            "Componente": [
                "1. Preço FOB Porto",
                "2. Custo Elevação Portuária",
                "3. Outras Taxas Portuárias",
                "4. Preço FAS Porto",
                "5. Frete Rodoviário até o Porto",
                "6. Fundo Estadual (FETHAB/FUNDEINFRA)",
                "7. Quebra Técnica / Impureza",
                "8. Funrural Retenção",
                "9. Margem Alvo da Trading",
                "➔ PREÇO PARIDADE BALCÃO LÍQUIDO",
            ],
            "R$/saca": [
                f"R$ {bk.fob_gross_brl_bag:.2f}",
                f"-R$ {bk.elevation_brl_bag:.2f}",
                f"-R$ {bk.other_port_costs_brl_bag:.2f}",
                f"R$ {bk.fas_brl_bag:.2f}",
                f"-R$ {bk.freight_brl_bag:.2f}",
                f"-R$ {bk.state_fund_brl_bag:.2f}",
                f"-R$ {bk.shrinkage_brl_bag:.2f}",
                f"-R$ {bk.funrural_brl_bag:.2f}",
                f"-R$ {bk.trading_margin_brl_bag:.2f}",
                f"R$ {bk.net_parity_brl_bag:.2f}",
            ],
            "R$/tonelada": [
                f"R$ {bk.fob_gross_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.elevation_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.other_port_costs_brl_bag / 0.06:,.2f}",
                f"R$ {bk.fas_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.freight_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.state_fund_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.shrinkage_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.funrural_brl_bag / 0.06:,.2f}",
                f"-R$ {bk.trading_margin_brl_bag / 0.06:,.2f}",
                f"R$ {bk.net_parity_brl_bag / 0.06:,.2f}",
            ],
        })
        st.dataframe(summary_df, hide_index=True, use_container_width=True)

    # Comparativo Multi-Praças
    st.markdown("<br>", unsafe_allow_html=True)
    st.write("##### 🗺️ Comparativo Regional de Paridade e Margem de Originação")
    batch_rows = []
    for h_id, hub in ORIGINATION_HUBS.items():
        c_price = market_service.get_cash_price(h_id, selected_commodity.value)
        p_inp = ParityCalculationInput(
            commodity=selected_commodity,
            cbot_price_cents=cbot_price,
            port_premium_cents=port_premium,
            usd_brl_fx=usd_brl,
            hub_id=h_id,
            port_id=selected_port_id,
            current_cash_price_brl_bag=c_price,
        )
        p_res = ExportParityEngine.calculate(p_inp)
        batch_rows.append({
            "Praça": hub.name,
            "Estado": hub.state,
            "Frete (R$/ton)": f"R$ {hub.freight_to_port_brl_ton.get(selected_port_id, 0.0):.2f}",
            "Paridade (R$/sc)": f"R$ {p_res.net_parity_price_brl_bag:.2f}",
            "Balcão Físico (R$/sc)": f"R$ {c_price:.2f}" if c_price else "-",
            "Spread Trading (R$/sc)": f"R$ {p_res.originator_spread_brl_bag:+.2f}" if p_res.originator_spread_brl_bag is not None else "-",
            "Margem (%)": f"{p_res.originator_margin_pct:+.2f}%" if p_res.originator_margin_pct is not None else "-",
        })
    df_batch = pd.DataFrame(batch_rows)
    st.dataframe(df_batch, hide_index=True, use_container_width=True)


# ==============================================================================
# TAB 2: CURVA FORWARD & CUSTO DE CARREGO
# ==============================================================================
with tab_forward:
    st.subheader("Análise de Custo de Carrego (Carry Trade: Vender Spot vs Forward)")
    st.markdown(
        f"<p style='color: #475569;'>Avalie se o spread entre contratos futuros/forward cobre os custos "
        f"de armazenagem física, custo financeiro de oportunidade (CDI) e quebra técnica de estoque.</p>",
        unsafe_allow_html=True,
    )

    c_col1, c_col2, c_col3 = st.columns(3)
    with c_col1:
        spot_name = st.text_input("Contrato Spot", value="Spot (Colheita / Março)")
        spot_price_in = st.number_input("Preço Spot Atual (R$/saca)", value=cash_price, step=0.5)
        
    with c_col2:
        forward_name = st.selectbox(
            "Contrato Futuro de Entrega",
            options=["Maio", "Julho", "Agosto", "Setembro"],
            index=1,
        )
        months_dict = {"Maio": 2.0, "Julho": 4.0, "Agosto": 5.0, "Setembro": 6.0}
        months_forward = months_dict[forward_name]
        default_fwd_price = round(spot_price_in + (months_forward * 2.20), 2)
        forward_price_in = st.number_input("Preço Forward Travado (R$/saca)", value=default_fwd_price, step=0.5)

    with c_col3:
        months_input = st.number_input("Prazo de Armazenagem (Meses)", min_value=0.5, max_value=18.0, value=months_forward, step=0.5)

    st.write("###### Parâmetros de Custos de Carrego")
    cost_p1, cost_p2, cost_p3 = st.columns(3)
    with cost_p1:
        storage_month = st.number_input("Tarifa de Armazenagem (R$/saca/mês)", value=0.65, step=0.05, help="Cobrança típica de armazém geral")
    with cost_p2:
        financial_month = st.number_input("Custo de Capital / CDI (% ao mês)", value=0.85, step=0.05, help="Taxa livre de risco ou custo do funding")
    with cost_p3:
        technical_loss = st.number_input("Quebra Técnica no Período (%)", value=0.25, step=0.05)

    # Executar Motor de Carrego
    carry_input = CarryCalculationInput(
        spot_contract_name=spot_name,
        forward_contract_name=forward_name,
        spot_price_brl_bag=spot_price_in,
        forward_price_brl_bag=forward_price_in,
        months_to_forward=months_input,
        storage_cost_brl_bag_month=storage_month,
        financial_cost_pct_month=financial_month,
        technical_loss_pct=technical_loss,
    )
    carry_res = CarryCostEngine.calculate(carry_input)

    st.markdown("<br>", unsafe_allow_html=True)

    # Banner de Decisão com Alto Contraste
    if "CARREGAR" in carry_res.recommendation:
        st.markdown(
            f"""
            <div style="background-color: #f0fdf4; border: 2px solid #16a34a; border-radius: 10px; padding: 20px 24px;">
                <div style="color: #166534; font-size: 1.3rem; font-weight: 700; margin-bottom: 6px;">
                    🚀 DECISÃO RECOMENDADA: {carry_res.recommendation}
                </div>
                <div style="color: #15803d; font-size: 1.0rem; line-height: 1.5;">
                    {carry_res.detailed_rationale}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif "VENDER" in carry_res.recommendation:
        st.markdown(
            f"""
            <div style="background-color: #fef2f2; border: 2px solid #dc2626; border-radius: 10px; padding: 20px 24px;">
                <div style="color: #991b1b; font-size: 1.3rem; font-weight: 700; margin-bottom: 6px;">
                    🛑 DECISÃO RECOMENDADA: {carry_res.recommendation}
                </div>
                <div style="color: #b91c1c; font-size: 1.0rem; line-height: 1.5;">
                    {carry_res.detailed_rationale}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="background-color: #fffbeb; border: 2px solid #d97706; border-radius: 10px; padding: 20px 24px;">
                <div style="color: #92400e; font-size: 1.3rem; font-weight: 700; margin-bottom: 6px;">
                    ⚖️ DECISÃO RECOMENDADA: {carry_res.recommendation}
                </div>
                <div style="color: #b45309; font-size: 1.0rem; line-height: 1.5;">
                    {carry_res.detailed_rationale}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    k_col1, k_col2, k_col3, k_col4 = st.columns(4)
    with k_col1:
        st.metric(
            label="Spread Bruto Forward",
            value=f"R$ {carry_res.gross_spread_brl_bag:+.2f} / sc",
            delta=f"{((carry_res.forward_price_brl_bag / carry_res.spot_price_brl_bag) - 1)*100:+.2f}%",
        )
    with k_col2:
        st.metric(
            label="Custo Total de Carrego",
            value=f"R$ {carry_res.total_carry_cost_brl_bag:.2f} / sc",
            delta=f"Armazém: R$ {carry_res.total_storage_cost_brl_bag:.2f}",
            delta_color="inverse",
        )
    with k_col3:
        st.metric(
            label="Resultado Líquido do Carrego",
            value=f"R$ {carry_res.net_carry_brl_bag:+.2f} / sc",
            delta="Margem Líquida Adicional",
            delta_color="normal" if carry_res.net_carry_brl_bag >= 0 else "inverse",
        )
    with k_col4:
        st.metric(
            label="Rentabilidade Anualizada",
            value=f"{carry_res.annualized_return_pct:+.2f}% a.a.",
            delta=f"Período: {carry_res.net_return_pct:+.2f}%",
        )

    # Gráfico de evolução do custo de carrego
    st.markdown("<br>", unsafe_allow_html=True)
    st.write("##### 📈 Evolução Mensal do Custo de Carrego (R$/saca)")
    time_points = [m for m in range(1, int(months_input) + 3)]
    sim_storage = [storage_month * m for m in time_points]
    sim_fin = [spot_price_in * (((1 + financial_month/100)**m) - 1) for m in time_points]
    sim_total = [stg + fn + (spot_price_in * technical_loss/100) for stg, fn in zip(sim_storage, sim_fin)]
    
    carry_chart_df = pd.DataFrame({
        "Mês": time_points,
        "Armazenagem Física": sim_storage,
        "Custo de Oportunidade (CDI)": sim_fin,
        "Custo Total Acumulado": sim_total,
    })
    
    carry_fig = px.line(
        carry_chart_df,
        x="Mês",
        y=["Armazenagem Física", "Custo de Oportunidade (CDI)", "Custo Total Acumulado"],
        color_discrete_map={
            "Armazenagem Física": "#d97706",
            "Custo de Oportunidade (CDI)": "#7c3aed",
            "Custo Total Acumulado": "#dc2626",
        },
    )
    carry_fig.add_hline(
        y=carry_res.gross_spread_brl_bag,
        line_dash="dash",
        line_color="#16a34a",
        annotation_text=f"Spread Bruto Forward (R$ {carry_res.gross_spread_brl_bag:.2f})",
        annotation_position="bottom right",
    )
    carry_fig.update_layout(
        template="plotly_white",
        font=dict(color="#0f172a", size=12),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        yaxis=dict(title="R$ por saca (60kg)", gridcolor="#f1f5f9"),
        xaxis=dict(title="Meses de Carregamento", gridcolor="#f1f5f9"),
        height=380,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(carry_fig, use_container_width=True)


# ==============================================================================
# TAB 3: SIMULADOR DE CENÁRIOS E ESTRESSE
# ==============================================================================
with tab_stress:
    st.subheader("⚡ Simulador de Estresse de Mercado & Análise de Sensibilidade")
    st.markdown(
        f"<p style='color: #475569;'>Avalie instantaneamente o impacto de choques simultâneos de "
        f"Câmbio, CBOT, Prêmios e Fretes Rodoviários na rentabilidade da operação.</p>",
        unsafe_allow_html=True,
    )

    sim_c1, sim_c2 = st.columns(2)
    with sim_c1:
        st.write("###### Configurar Cenário de Choque")
        fx_shock = st.slider("Choque no Dólar (%)", min_value=-20.0, max_value=20.0, value=-5.0, step=1.0)
        cbot_shock = st.slider("Choque em Chicago / CBOT (cents/bu)", min_value=-150.0, max_value=150.0, value=0.0, step=5.0)
        premium_shock = st.slider("Choque no Prêmio do Porto (cents/bu)", min_value=-50.0, max_value=50.0, value=-10.0, step=5.0)
        freight_shock = st.slider("Choque no Frete Rodoviário (%)", min_value=-25.0, max_value=50.0, value=10.0, step=5.0)

    # Executar Simulação
    scenario_input = ScenarioSimulationInput(
        base_input=parity_input,
        fx_shift_pct=fx_shock,
        cbot_shift_cents=cbot_shock,
        premium_shift_cents=premium_shock,
        freight_shift_pct=freight_shock,
    )
    sim_res = StressTesterEngine.simulate_scenario(scenario_input)

    with sim_c2:
        st.write("###### Impacto Comparativo")
        s_res1, s_res2 = st.columns(2)
        with s_res1:
            st.metric(
                label="Paridade Balcão Base",
                value=f"R$ {sim_res.base_parity_brl_bag:.2f} / sc",
            )
            st.metric(
                label="Variação Absoluta",
                value=f"R$ {sim_res.diff_brl_bag:+.2f} / sc",
                delta=f"{sim_res.diff_pct:+.2f}%",
                delta_color="normal" if sim_res.diff_brl_bag >= 0 else "inverse",
            )
        with s_res2:
            st.metric(
                label="Paridade Balcão Simulada",
                value=f"R$ {sim_res.simulated_parity_brl_bag:.2f} / sc",
                delta=f"{sim_res.diff_brl_bag:+.2f} / sc",
            )
            if sim_res.simulated_margin_brl_bag is not None:
                st.metric(
                    label="Margem de Originação Simulada",
                    value=f"R$ {sim_res.simulated_margin_brl_bag:+.2f} / sc",
                    delta_color="normal" if sim_res.simulated_margin_brl_bag >= 0 else "inverse",
                )

    st.markdown("<br>", unsafe_allow_html=True)
    st.write("##### 🌡️ Matriz de Sensibilidade: Dólar vs Chicago (R$/saca)")
    st.caption("Preço de Paridade Balcão resultante para combinações de taxa cambial e CBOT.")

    # Matriz de Sensibilidade
    matrix_df = StressTesterEngine.generate_sensitivity_matrix(parity_input)
    
    heatmap_fig = px.imshow(
        matrix_df,
        labels=dict(x="Variação CBOT", y="Variação Câmbio", color="Paridade (R$/sc)"),
        x=matrix_df.columns,
        y=matrix_df.index,
        color_continuous_scale="YlGnBu",
        text_auto=".2f",
        aspect="auto",
    )
    heatmap_fig.update_layout(
        template="plotly_white",
        font=dict(color="#0f172a", size=12),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        height=420,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(heatmap_fig, use_container_width=True)


# ==============================================================================
# TAB 4: CUSTOS LOGÍSTICOS E FISCAIS
# ==============================================================================
with tab_tabelas:
    st.subheader("Tabelas de Referência Logística e Tributária")
    st.markdown(
        f"<p style='color: #475569;'>Parâmetros de fretes rodoviários, taxas portuárias e "
        f"fundos agropecuários estaduais cadastrados.</p>",
        unsafe_allow_html=True,
    )

    tab_c1, tab_c2 = st.columns(2)
    with tab_c1:
        st.write("##### 🚛 Fretes Rodoviários por Rota (R$/tonelada)")
        freight_data = []
        for h_id, hub in ORIGINATION_HUBS.items():
            for p_id, f_val in hub.freight_to_port_brl_ton.items():
                freight_data.append({
                    "Origem": hub.name,
                    "Estado": hub.state,
                    "Porto Destino": PORTS[p_id].name,
                    "Frete (R$/ton)": f"R$ {f_val:.2f}",
                    "Equiv. (R$/saca)": f"R$ {f_val * 0.06:.2f}",
                })
        st.dataframe(pd.DataFrame(freight_data), hide_index=True, use_container_width=True)

    with tab_c2:
        st.write("##### 🚢 Despesas e Elevação Portuária")
        port_data = []
        for p_id, port in PORTS.items():
            port_data.append({
                "Porto": port.name,
                "UF": port.state,
                "Elevação (USD/ton)": f"${port.elevation_cost_usd_ton:.2f}",
                "Outras Taxas (R$/ton)": f"R$ {port.other_port_costs_brl_ton:.2f}",
            })
        st.dataframe(pd.DataFrame(port_data), hide_index=True, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.write("##### 🏛️ Fundos Tributários Estaduais Incidentes")
        tax_data = [
            {"Estado": "Mato Grosso (MT)", "Tributo": "FETHAB", "Soja (R$/sc)": "R$ 2,85", "Milho (R$/sc)": "R$ 1,45", "Finalidade": "Fundo Estadual de Transporte e Habitação"},
            {"Estado": "Goiás (GO)", "Tributo": "FUNDEINFRA", "Soja (R$/sc)": "R$ 1,65", "Milho (R$/sc)": "R$ 0,90", "Finalidade": "Fundo Estadual de Infraestrutura"},
            {"Estado": "Paraná (PR)", "Tributo": "Isento", "Soja (R$/sc)": "R$ 0,00", "Milho (R$/sc)": "R$ 0,00", "Finalidade": "Imunidade de ICMS (Lei Kandir)"},
            {"Estado": "Rio Grande do Sul (RS)", "Tributo": "Isento", "Soja (R$/sc)": "R$ 0,00", "Milho (R$/sc)": "R$ 0,00", "Finalidade": "Imunidade de ICMS"},
            {"Estado": "Bahia (BA)", "Tributo": "PRODEAGRO", "Soja (R$/sc)": "R$ 0,60", "Milho (R$/sc)": "R$ 0,35", "Finalidade": "Fundo de desenvolvimento agropecuário"},
        ]
        st.dataframe(pd.DataFrame(tax_data), hide_index=True, use_container_width=True)


# ==============================================================================
# TAB 5: BANCO DE DADOS & HISTÓRICO
# ==============================================================================
with tab_database:
    st.subheader("🗄️ Repositório Relacional de Market Data & Governança")
    st.markdown(
        f"<p style='color: #475569;'>Cotações ativas persistidas na base relacional PostgreSQL, "
        f"consultas de séries temporais históricas e registros de auditoria ETL.</p>",
        unsafe_allow_html=True,
    )

    try:
        with SessionLocal() as db:
            all_quotes = MarketDataRepository.get_all_latest_quotes(db)
            recent_logs = db.query(ExtractionLog).order_by(ExtractionLog.id.desc()).limit(5).all()
            
            # KPIs do Banco de Dados com visual claro
            db_col1, db_col2, db_col3 = st.columns(3)
            with db_col1:
                st.metric("Total de Cotações Ativas", len(all_quotes))
            with db_col2:
                last_log_status = recent_logs[0].status if recent_logs else "Nenhum"
                st.metric("Status do Último Pipeline ETL", last_log_status)
            with db_col3:
                last_exec = recent_logs[0].started_at.strftime("%d/%m/%Y %H:%M:%S") if recent_logs else "-"
                st.metric("Última Execução ETL", last_exec)

            st.markdown("<br>", unsafe_allow_html=True)

            # Tabela de Cotações Persistidas com Filtro
            st.write("##### 📋 Cotações Ativas na Base de Dados")
            categories = ["TODAS"] + sorted(list({q.category for q in all_quotes})) if all_quotes else ["TODAS"]
            selected_cat = st.selectbox("Filtrar por Categoria", categories, index=0)

            filtered_quotes = all_quotes
            if selected_cat != "TODAS":
                filtered_quotes = [q for q in all_quotes if q.category == selected_cat]

            if filtered_quotes:
                quotes_df = pd.DataFrame([
                    {
                        "Data": q.quote_date.strftime("%d/%m/%Y") if q.quote_date else "-",
                        "Categoria": q.category,
                        "Símbolo": q.symbol,
                        "Commodity": q.commodity or "-",
                        "Praça / Local": q.location_id or "-",
                        "Preço": f"{q.price:.4f}" if q.category == "FX" else f"{q.price:.2f}",
                        "Unidade": q.unit,
                        "Fonte": q.source,
                        "Horário": q.timestamp.strftime("%H:%M:%S") if q.timestamp else "-",
                    }
                    for q in filtered_quotes
                ])
                st.dataframe(quotes_df, hide_index=True, use_container_width=True)
            else:
                st.info("Nenhuma cotação encontrada no banco. Clique no botão '⚡ Extrair & Persistir Market Data' na barra lateral para popular a base!")

            # Histórico e Gráficos
            if all_quotes:
                st.markdown("<br>", unsafe_allow_html=True)
                st.write("##### 📈 Consulta de Série Histórica por Ativo")
                symbols_available = sorted(list({q.symbol for q in all_quotes}))
                chosen_symbol = st.selectbox("Selecione o Ativo para Análise Temporal", symbols_available)
                
                history_quotes = MarketDataRepository.get_quotes_history(db, chosen_symbol, limit=30)
                if history_quotes:
                    hist_df = pd.DataFrame([
                        {
                            "Data": h.quote_date,
                            "Preço": h.price,
                            "Fonte": h.source,
                        }
                        for h in reversed(history_quotes)
                    ])
                    fig_hist = px.line(
                        hist_df,
                        x="Data",
                        y="Preço",
                        markers=True,
                        title=f"Evolução Temporal: {chosen_symbol}",
                        color_discrete_sequence=["#16a34a"],
                    )
                    fig_hist.update_layout(
                        template="plotly_white",
                        font=dict(color="#0f172a", size=12),
                        paper_bgcolor="#ffffff",
                        plot_bgcolor="#ffffff",
                        height=350,
                        margin=dict(l=20, r=20, t=40, b=20),
                        yaxis=dict(gridcolor="#f1f5f9"),
                        xaxis=dict(gridcolor="#f1f5f9"),
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)

            # Logs de Auditoria
            st.markdown("<br>", unsafe_allow_html=True)
            st.write("##### 🛡️ Auditoria de Execuções ETL (Extraction Logs)")
            if recent_logs:
                logs_df = pd.DataFrame([
                    {
                        "ID": l.id,
                        "Início": l.started_at.strftime("%d/%m/%Y %H:%M:%S") if l.started_at else "-",
                        "Fim": l.finished_at.strftime("%d/%m/%Y %H:%M:%S") if l.finished_at else "-",
                        "Status": l.status,
                        "Extraídos": l.records_extracted,
                        "Persistidos (Upsert)": l.records_upserted,
                        "Fontes": l.sources_contacted,
                    }
                    for l in recent_logs
                ])
                st.dataframe(logs_df, hide_index=True, use_container_width=True)
            else:
                st.write("Nenhum log registrado ainda.")

    except Exception as e:
        st.error(f"Erro ao conectar com a base de dados: {e}")
