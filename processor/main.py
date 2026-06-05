import sys
import os
import ssl
import asyncio  # Add this here

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from common.config import settings
from common.database import engine  # Add these
from common.models import Base       # Add these

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# 1. Build the SSL context
ctx = None
if settings.KAFKA_SASL_ENABLED and "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

# 2. Build SASL Credentials
broker_credentials = None
if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM or "PLAIN",
        ssl_context=ctx
    )

# 3. Initialize the Faust App
app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",
    broker_credentials=broker_credentials,
    datadir='/app/rocksdb_data',
    topic_allow_declare=False,
    topic_partitions=3,
    autodiscover=['processor.agents']
)

app.conf.leader_election = False

# 4. Helper function to ensure tables exist
async def ensure_tables_exist():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

def main() -> None:
    # Trigger the table creation before Faust boots up
    try:
        asyncio.run(ensure_tables_exist())
        print("Database schema verified.")
    except Exception as e:
        print(f"Error verifying database schema: {e}")
        
    app.main()

if __name__ == '__main__':
    main()
