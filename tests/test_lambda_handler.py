"""
Testes unitários para o AWS Lambda Handler (API Gateway e EventBridge Scheduler).
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from src.api.lambda_handler import handler


def test_lambda_handler_eventbridge_b3_settlement():
    """Valida se o handler identifica e executa a rotina de fechamento B3 via EventBridge."""
    event = {
        "source": "aws.events",
        "detail-type": "Scheduled Event",
        "job_type": "B3_SETTLEMENT",
    }

    with patch("src.services.b3_extractor.extract_and_persist_b3_data") as mock_extract:
        mock_extract.return_value = {"status": "SUCCESS", "total_persisted": 9}
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "SUCCESS"
        assert body["job_type"] == "B3_SETTLEMENT"
        mock_extract.assert_called_once_with(session_type="EOD_SETTLEMENT")


def test_lambda_handler_eventbridge_b3_intraday():
    """Valida se o handler identifica e executa a rotina intraday da B3."""
    event = {
        "trigger": "eventbridge",
        "job_type": "B3_INTRADAY",
    }

    with patch("src.services.b3_extractor.extract_and_persist_b3_data") as mock_extract:
        mock_extract.return_value = {"status": "SUCCESS", "total_persisted": 9}
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["job_type"] == "B3_INTRADAY"
        mock_extract.assert_called_once_with(session_type="INTRADAY")


def test_lambda_handler_eventbridge_macro_market_data():
    """Valida se o handler identifica e executa a rotina de market data macro."""
    event = {
        "source": "aws.events",
        "job_type": "MACRO_MARKET_DATA",
    }

    with patch("src.services.extractor.extract_and_persist_market_data") as mock_extract:
        mock_extract.return_value = {"status": "SUCCESS", "total_persisted": 25}
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["job_type"] == "MACRO_MARKET_DATA"
        mock_extract.assert_called_once()
