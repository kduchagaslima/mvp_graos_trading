"""
Motor de Projeção de Curva Forward e Análise de Custo de Carrego (Cost of Carry).
Determina a viabilidade entre vender a commodity no spot ou armazenar para entrega futura.
"""

from src.domain.models import CarryCalculationInput, CarryCalculationResult


class CarryCostEngine:
    """
    Calcula se o spread entre contratos futuros/forward remunera o custo de armazenagem,
    juros/custo de oportunidade do capital (CDI) e quebra técnica de estoque.
    """

    @classmethod
    def calculate(cls, inp: CarryCalculationInput) -> CarryCalculationResult:
        gross_spread = inp.forward_price_brl_bag - inp.spot_price_brl_bag

        # 0. Cálculo do prazo em meses (datas explícitas ou meses diretos)
        if inp.spot_date and inp.forward_date:
            days_delta = (inp.forward_date - inp.spot_date).days
            if days_delta <= 0:
                raise ValueError("A data de entrega futura (forward_date) deve ser posterior à data spot (spot_date).")
            months = round(days_delta / 30.4167, 2)
        else:
            months = inp.months_to_forward

        # 1. Custo de Armazenagem Física
        total_storage = inp.storage_cost_brl_bag_month * months

        # 2. Custo Financeiro / Oportunidade do Capital
        # Convenção anual efetiva: (1 + i)^(1/12) - 1 se informada taxa anual
        if inp.financial_cost_annual_pct is not None and inp.financial_cost_annual_pct > 0:
            monthly_rate = ((1.0 + (inp.financial_cost_annual_pct / 100.0)) ** (1.0 / 12.0)) - 1.0
            effective_monthly_pct = monthly_rate * 100.0
        else:
            effective_monthly_pct = inp.financial_cost_pct_month
            monthly_rate = effective_monthly_pct / 100.0

        total_financial = inp.spot_price_brl_bag * (((1.0 + monthly_rate) ** months) - 1.0)

        # 3. Quebra técnica no armazém (secagem, impureza, movimentação)
        total_technical_loss = inp.spot_price_brl_bag * (inp.technical_loss_pct / 100.0)

        # Custo total de carrego
        total_carry_cost = total_storage + total_financial + total_technical_loss

        # Resultado líquido do carrego (Net Carry)
        net_carry = gross_spread - total_carry_cost
        
        # Rentabilidade líquida e anualizada
        net_return_pct = (net_carry / inp.spot_price_brl_bag) * 100.0
        annualized_return_pct = (
            (net_return_pct * (12.0 / months)) if months > 0 else 0.0
        )

        # Recomendações padronizadas e unificadas
        if net_carry > 0.75:
            recommendation_code = "POSITIVE_CARRY"
            recommendation = "CARREGAR PARA VENDA FUTURA"
            rationale = (
                f"O prêmio da curva forward (spread de R$ {gross_spread:.2f}/sc) supera os custos totais "
                f"de carrego (R$ {total_carry_cost:.2f}/sc), gerando um ganho líquido adicional de "
                f"R$ {net_carry:.2f}/saca ({annualized_return_pct:.1f}% a.a. acima do CDI)."
            )
        elif net_carry < -0.75:
            recommendation_code = "NEGATIVE_CARRY"
            recommendation = "VENDER SPOT IMEDIATAMENTE"
            rationale = (
                f"Carregar o grão geraria um prejuízo líquido de R$ {abs(net_carry):.2f}/saca. "
                f"O spread forward de R$ {gross_spread:.2f}/sc não remunera os custos de armazenagem "
                f"e o custo de oportunidade do capital (R$ {total_carry_cost:.2f}/sc)."
            )
        else:
            recommendation_code = "NEUTRAL"
            recommendation = "NEUTRO / INDIFERENTE"
            rationale = (
                f"O spread da curva forward (R$ {gross_spread:.2f}/sc) empata praticamente com os custos "
                f"de carrego (R$ {total_carry_cost:.2f}/sc). Avaliar riscos logísticos e capacidade de armazenagem."
            )

        return CarryCalculationResult(
            spot_price_brl_bag=round(inp.spot_price_brl_bag, 2),
            forward_price_brl_bag=round(inp.forward_price_brl_bag, 2),
            gross_spread_brl_bag=round(gross_spread, 2),
            months=months,
            effective_monthly_rate_pct=round(effective_monthly_pct, 4),
            total_storage_cost_brl_bag=round(total_storage, 2),
            total_financial_cost_brl_bag=round(total_financial, 2),
            total_technical_loss_brl_bag=round(total_technical_loss, 2),
            total_carry_cost_brl_bag=round(total_carry_cost, 2),
            net_carry_brl_bag=round(net_carry, 2),
            net_return_pct=round(net_return_pct, 2),
            annualized_return_pct=round(annualized_return_pct, 2),
            recommendation=recommendation,
            recommendation_code=recommendation_code,
            detailed_rationale=rationale,
        )
