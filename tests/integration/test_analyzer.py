import pytest
from salesforce_ai_engineer.recovery.analyzer import FailureAnalyzer
from salesforce_ai_engineer.recovery.models import FailureCategory

@pytest.mark.asyncio
async def test_categorize_salesforce_errors():
    """Verify the analyzer catches specific Salesforce error strings."""
    
    # Test Session Expiry
    cat_auth = await FailureAnalyzer.categorize_error("INVALID_SESSION_ID: Session expired or invalid")
    assert cat_auth == FailureCategory.AUTHENTICATION
    
    # Test Governor Limits
    cat_limit = await FailureAnalyzer.categorize_error("System.LimitException: Too many SOQL queries: 101")
    assert cat_limit == FailureCategory.GOVERNOR_LIMIT
    
    # Test Metadata issues
    cat_meta = await FailureAnalyzer.categorize_error("field_integrity_exception: invalid bit on record")
    assert cat_meta == FailureCategory.METADATA

    print("✅ FailureAnalyzer pattern matching passed.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_categorize_salesforce_errors())