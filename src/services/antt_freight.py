"""
Módulo de Cálculo e Conformidade da Tabela de Frete Piso Mínimo da ANTT.
Em conformidade com a Lei nº 13.703/2018 e Resolução ANTT nº 5.867/2020 (atualizada por portarias SUROC).

Calcula os custos mínimos regulatórios de transporte rodoviário para Granel Sólido (Soja e Milho),
considerando coeficientes de custo de deslocamento (CC) e custo de carga/descarga (CCD).
"""

from typing import Dict, Any, List, Optional
from src.domain.locations import ORIGINATION_HUBS, PORTS
from src.services.market_data import ROUTE_DISTANCES_KM


# Coeficientes oficiais ANTT para Granel Sólido (Carga Lotação)
# Atualizados conforme tabelas vigentes da ANTT (Resolução nº 5.867/2020)
ANTT_COEFFICIENTS = {
    # Bitrem / Veículo 7 Eixos (Capacidade líquida média: 37 toneladas úteis)
    "7_EIXOS_BITREM": {
        "name": "Bitrem (7 Eixos)",
        "axles": 7,
        "payload_tons": 37.0,
        "cc_brl_km": 5.8504,     # Custo de Deslocamento (R$/km)
        "ccd_fixed_brl": 482.15,  # Custo de Carga e Descarga (R$ fixo por viagem)
    },
    # Rodotrem / Veículo 9 Eixos (Capacidade líquida média: 49 toneladas úteis) - padrão corredores longos MT/GO/BA
    "9_EIXOS_RODOTREM": {
        "name": "Rodotrem (9 Eixos)",
        "axles": 9,
        "payload_tons": 49.0,
        "cc_brl_km": 7.1245,     # Custo de Deslocamento (R$/km)
        "ccd_fixed_brl": 584.30,  # Custo de Carga e Descarga (R$ fixo por viagem)
    },
}


class ANTTFreightService:
    """
    Serviço de cálculo dos pisos mínimos regulatórios da ANTT e análise de conformidade de fretes.
    """

    @classmethod
    def calculate_floor_rate(
        cls,
        distance_km: int,
        vehicle_type: str = "9_EIXOS_RODOTREM",
    ) -> Dict[str, Any]:
        """
        Calcula o piso mínimo regulatório da ANTT para uma distância em km.
        Fórmula: Custo Total = (CC * distância) + CCD
                 Preço/ton = Custo Total / Carga Útil
        """
        coeffs = ANTT_COEFFICIENTS.get(vehicle_type, ANTT_COEFFICIENTS["9_EIXOS_RODOTREM"])
        dist = max(1, distance_km)
        trip_cost_brl = (coeffs["cc_brl_km"] * dist) + coeffs["ccd_fixed_brl"]
        floor_brl_ton = round(trip_cost_brl / coeffs["payload_tons"], 2)
        floor_brl_bag = round(floor_brl_ton * 0.06, 2)

        return {
            "vehicle_type": vehicle_type,
            "vehicle_name": coeffs["name"],
            "axles": coeffs["axles"],
            "payload_tons": coeffs["payload_tons"],
            "distance_km": dist,
            "cc_brl_km": coeffs["cc_brl_km"],
            "ccd_fixed_brl": coeffs["ccd_fixed_brl"],
            "trip_total_minimum_brl": round(trip_cost_brl, 2),
            "floor_rate_brl_ton": floor_brl_ton,
            "floor_rate_brl_bag": floor_brl_bag,
            "legal_basis": "Lei nº 13.703/2018 / Resolução ANTT nº 5.867/2020",
        }

    @classmethod
    def get_corridors_compliance_summary(cls, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Retorna todos os corredores cadastrados com comparativo entre frete praticado de mercado
        e os pisos mínimos regulatórios da ANTT (7 e 9 eixos).
        """
        from src.services.market_data import market_service

        results = []
        for (orig_id, dest_id), dist_km in ROUTE_DISTANCES_KM.items():
            hub = ORIGINATION_HUBS.get(orig_id)
            port = PORTS.get(dest_id)
            if not hub or not port:
                continue

            current_market_rate = market_service.get_freight_rate(orig_id, dest_id, db=db)

            # Cálculo para 7 e 9 eixos
            floor_7 = cls.calculate_floor_rate(dist_km, vehicle_type="7_EIXOS_BITREM")
            floor_9 = cls.calculate_floor_rate(dist_km, vehicle_type="9_EIXOS_RODOTREM")

            # Avaliação de conformidade com base no rodotrem 9 eixos (veículo dominante nos corredores)
            benchmark_floor = floor_9["floor_rate_brl_ton"]
            diff_brl_ton = round(current_market_rate - benchmark_floor, 2)
            diff_pct = round((diff_brl_ton / benchmark_floor) * 100, 2) if benchmark_floor > 0 else 0.0

            if diff_brl_ton >= 0:
                compliance_status = "ABOVE_FLOOR"
                compliance_label = "Conforme (Acima do Piso)"
            else:
                compliance_status = "BELOW_FLOOR"
                compliance_label = "Risco (Abaixo do Piso Legal)"

            results.append({
                "origin_id": orig_id,
                "origin_name": hub.name,
                "origin_state": hub.state,
                "destination_id": dest_id,
                "destination_name": port.name,
                "destination_state": port.state,
                "distance_km": dist_km,
                "market_freight_brl_ton": round(current_market_rate, 2),
                "market_freight_brl_bag": round(current_market_rate * 0.06, 2),
                "antt_floor_7_axles_brl_ton": floor_7["floor_rate_brl_ton"],
                "antt_floor_9_axles_brl_ton": floor_9["floor_rate_brl_ton"],
                "antt_floor_brl_ton": benchmark_floor,
                "antt_floor_brl_bag": floor_9["floor_rate_brl_bag"],
                "spread_vs_floor_brl_ton": diff_brl_ton,
                "spread_vs_floor_pct": diff_pct,
                "compliance_status": compliance_status,
                "compliance_label": compliance_label,
            })

        return sorted(results, key=lambda x: (x["origin_name"], x["destination_name"]))
