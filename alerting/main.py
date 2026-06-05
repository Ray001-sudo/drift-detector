import asyncio
from alerting.rule_engine import app, refresh_rules

if __name__ == '__main__':
    # Initial load of rules
    asyncio.run(refresh_rules())
    app.main()
