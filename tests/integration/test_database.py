import pytest
from sqlalchemy import select
from common.models import User, AlertRule
from tests.factories import UserFactory, AlertRuleFactory

@pytest.mark.asyncio
async def test_create_user(db_session):
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()
    
    stmt = select(User).where(User.username == user.username)
    result = await db_session.execute(stmt)
    db_user = result.scalar_one()
    
    assert db_user is not None
    assert db_user.username == user.username

@pytest.mark.asyncio
async def test_create_alert_rule(db_session):
    rule = AlertRuleFactory.build()
    db_session.add(rule)
    await db_session.commit()
    
    stmt = select(AlertRule).where(AlertRule.feature_name == rule.feature_name)
    result = await db_session.execute(stmt)
    db_rule = result.scalar_one()
    
    assert db_rule is not None
    assert db_rule.threshold == 0.15
