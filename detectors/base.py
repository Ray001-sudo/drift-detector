from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple
from datetime import datetime

class BaseDriftDetector(ABC):
    
    @abstractmethod
    def detect(self, reference_data: Any, production_data: Any, feature_name: str) -> Dict[str, Any]:
        """
        Compute drift between reference and production data.
        Must return a dict containing at least:
        - score: float
        - is_drifted: bool
        - feature_name: str
        - timestamp: datetime
        """
        pass
