"""
Motor de Simulação de Cenários e Testes de Estresse de Paridade e Margem.
Permite simular choques em Câmbio (USD/BRL), CBOT, Prêmios e Frete Rodoviário.
"""

from typing import List, Dict, Any
from copy import deepcopy
import pandas as pd

from src.domain.models import (
    ParityCalculationInput,
    ScenarioSimulationInput,
    ScenarioSimulationResult,
)
from src.engines.export_parity import ExportParityEngine
from src.domain.locations import ORIGINATION_HUBS


class StressTesterEngine:
    """
    Executa testes de sensibilidade e gera matrizes de impacto para a mesa de trading.
    """

    @classmethod
    def simulate_scenario(cls, sim_input: ScenarioSimulationInput) -> ScenarioSimulationResult:
        base_inp = sim_input.base_input
        base_res = ExportParityEngine.calculate(base_inp)

        # Clonar e aplicar choques
        sim_inp_dict = base_inp.model_dump()
        
        # Choque cambial
        new_fx = base_inp.usd_brl_fx * (1.0 + (sim_input.fx_shift_pct / 100.0))
        sim_inp_dict["usd_brl_fx"] = round(new_fx, 4)

        # Choque CBOT
        new_cbot = base_inp.cbot_price_cents + sim_input.cbot_shift_cents
        sim_inp_dict["cbot_price_cents"] = round(new_cbot, 2)

        # Choque de Prêmio
        new_premium = base_inp.port_premium_cents + sim_input.premium_shift_cents
        sim_inp_dict["port_premium_cents"] = round(new_premium, 2)

        # Choque de Frete Rodoviário
        hub = ORIGINATION_HUBS.get(base_inp.hub_id)
        default_freight = hub.freight_to_port_brl_ton.get(base_inp.port_id, 300.0) if hub else 300.0
        current_freight = base_inp.freight_brl_ton if base_inp.freight_brl_ton is not None else default_freight
        new_freight = current_freight * (1.0 + (sim_input.freight_shift_pct / 100.0))
        sim_inp_dict["freight_brl_ton"] = round(new_freight, 2)

        sim_obj = ParityCalculationInput(**sim_inp_dict)
        sim_res = ExportParityEngine.calculate(sim_obj)

        diff_brl_bag = sim_res.net_parity_price_brl_bag - base_res.net_parity_price_brl_bag
        diff_pct = (diff_brl_bag / base_res.net_parity_price_brl_bag) * 100.0

        return ScenarioSimulationResult(
            base_parity_brl_bag=base_res.net_parity_price_brl_bag,
            simulated_parity_brl_bag=sim_res.net_parity_price_brl_bag,
            diff_brl_bag=round(diff_brl_bag, 2),
            diff_pct=round(diff_pct, 2),
            base_margin_brl_bag=base_res.originator_spread_brl_bag,
            simulated_margin_brl_bag=sim_res.originator_spread_brl_bag,
            applied_shifts={
                "fx_shift_pct": sim_input.fx_shift_pct,
                "cbot_shift_cents": sim_input.cbot_shift_cents,
                "premium_shift_cents": sim_input.premium_shift_cents,
                "freight_shift_pct": sim_input.freight_shift_pct,
            },
        )

    @classmethod
    def generate_sensitivity_matrix(
        cls,
        base_input: ParityCalculationInput,
        fx_steps_pct: List[float] = [-10.0, -5.0, 0.0, 5.0, 10.0],
        cbot_steps_cents: List[float] = [-60.0, -30.0, 0.0, 30.0, 60.0],
    ) -> pd.DataFrame:
        """
        Gera uma matriz bidimensional de sensibilidade (Câmbio vs CBOT)
        indicando o Preço de Paridade Balcão resultante (R$/saca).
        """
        matrix_data: Dict[str, List[float]] = {}
        
        for cbot_shift in cbot_steps_cents:
            col_label = f"CBOT {cbot_shift:+.0f}c"
            matrix_data[col_label] = []
            
            for fx_shift in fx_steps_pct:
                sim_req = ScenarioSimulationInput(
                    base_input=base_input,
                    fx_shift_pct=fx_shift,
                    cbot_shift_cents=cbot_shift,
                )
                res = cls.simulate_scenario(sim_req)
                matrix_data[col_label].append(res.simulated_parity_brl_bag)
                
        row_labels = [f"Dólar {fx:+.1f}%" for fx in fx_steps_pct]
        df = pd.DataFrame(matrix_data, index=row_labels)
        return df
