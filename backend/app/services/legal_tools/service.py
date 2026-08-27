"""
Legal Tools - Main service class composing all mixins.
"""

from app.config import settings

from ._case_lookup import CaseLookupMixin
from ._dockets import DocketsMixin
from ._helpers import HelpersMixin
from ._oral_arguments import OralArgumentsMixin
from ._precedents import PrecedentsMixin
from ._trends import TrendsMixin


class LegalToolsService(
    HelpersMixin,
    CaseLookupMixin,
    PrecedentsMixin,
    DocketsMixin,
    OralArgumentsMixin,
    TrendsMixin,
):
    """
    Comprehensive legal research tools using CourtListener API.
    """

    def __init__(self):
        token = getattr(settings, "courtlistener_api_token", None)
        # Treat empty string as None
        self.api_token = token if token and token.strip() else None
        self.headers = {"Accept": "application/json"}
        if self.api_token:
            self.headers["Authorization"] = f"Token {self.api_token}"
