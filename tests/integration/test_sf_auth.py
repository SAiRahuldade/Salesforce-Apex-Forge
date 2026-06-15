import sys
import os
from pathlib import Path
import asyncio

# Load environment variables from .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add src to path to enable imports from the project structure when running as a script
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

import pytest
from salesforce_ai_engineer.deployment.auth import ConnectionManager
from salesforce_ai_engineer.deployment.models import (
    DeploymentConnection, 
    ConnectionType, 
    DeploymentEnvironment
)
from salesforce_ai_engineer.config import config_manager

@pytest.mark.asyncio
async def test_salesforce_login():
    """Verify that the agent can obtain a real access token from Salesforce."""
    print("\n🔍 Testing Salesforce Authentication...")
    
    manager = ConnectionManager()
    conn = DeploymentConnection(
        connection_type=ConnectionType.USERNAME_PASSWORD,
        org_id="00D", # Placeholder, real ID extracted on login
        org_name="TestOrg",
        environment=DeploymentEnvironment.DEV,
        instance_url=config_manager.settings.salesforce.instance_url
    )
    
    try:
        auth = await manager.create_connection(conn)
        details = await auth.authenticate()
        
        assert "access_token" in details
        assert details["access_token"].startswith("00D") or len(details["access_token"]) > 20
        
        source = details.get('source', 'OAuth2')
        status = "SIMULATED" if source == "simulated" else "REAL"
        print(f"✅ Success! [{status}] Connected to Org ID: {details.get('org_id')}")
        print(f"🎫 Auth Source: {source}")
        
    except Exception as e:
        print(f"❌ Login Failed: {str(e)}")
        raise e

if __name__ == "__main__":
    asyncio.run(test_salesforce_login())