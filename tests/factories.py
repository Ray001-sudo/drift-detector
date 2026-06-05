import factory # type: ignore
import uuid
from common.models import User, AlertRule
from common.security import get_password_hash

class UserFactory(factory.Factory):
    class Meta:
        model = User
    
    id = factory.LazyFunction(uuid.uuid4)
    username = factory.Sequence(lambda n: f"user_{n}")
    password_hash = factory.LazyFunction(lambda: get_password_hash("TestPass123!"))
    role = "viewer"
    is_active = True

class AlertRuleFactory(factory.Factory):
    class Meta:
        model = AlertRule
        
    id = factory.LazyFunction(uuid.uuid4)
    feature_name = "age"
    detector_type = "kl"
    threshold = 0.15
    severity = "warning"
    is_active = True
