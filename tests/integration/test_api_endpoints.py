import pytest
from httpx import AsyncClient
from dashboard.main import app
from common.security import create_access_token

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
    # Because we don't have db/redis spun up in simple async context, might return down
    assert response.status_code == 200
    assert "status" in response.json()

@pytest.mark.asyncio
async def test_get_scores_unauthorized():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/v1/drift/scores")
    assert response.status_code == 401

# We can't fully test authenticated endpoints without a DB fixture loaded with the user
# But we can verify the 401 behavior and structure.
