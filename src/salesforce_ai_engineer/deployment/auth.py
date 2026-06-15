"""Salesforce authentication and connection management."""

from __future__ import annotations

import logging
import httpx
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, TYPE_CHECKING
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.deployment.models import (
    DeploymentConnection,
    ConnectionType,
    DeploymentEnvironment,
)
from salesforce_ai_engineer.config import config_manager

if TYPE_CHECKING:
    from salesforce_ai_engineer.deployment.cli_helper import SalesforceCliHelper

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class SalesforceAuthError(Exception):
    """Base exception for authentication errors."""

    pass


class SalesforceAuth(ABC):
    """Abstract base class for Salesforce authentication."""

    def __init__(self, connection: DeploymentConnection):
        """Initialize auth handler.

        Args:
            connection: DeploymentConnection configuration
        """
        self.connection = connection
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.logger = logger

    @abstractmethod
    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate and obtain access token.

        Returns:
            Dictionary with authentication details
        """
        pass

    @abstractmethod
    async def validate(self) -> bool:
        """Validate authentication is still valid.

        Returns:
            True if authenticated and valid
        """
        pass

    @abstractmethod
    async def refresh(self) -> bool:
        """Refresh authentication token if needed.

        Returns:
            True if refresh successful
        """
        pass

    async def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authentication.

        Returns:
            Headers dictionary for API calls
        """
        if not self.access_token:
            await self.authenticate()

        if not await self.validate():
            await self.refresh()

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


class JWTAuth(SalesforceAuth):
    """JWT Bearer Token authentication."""

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate using JWT.

        Returns:
            Authentication details
        """
        self.logger.info(
            f"Authenticating with JWT for org: {self.connection.org_id}"
        )

        # Simulate JWT authentication when sf CLI is unavailable
        self.access_token = f"jwt_token_{self.connection.org_id}"
        self.token_expiry = datetime.now(UTC) + timedelta(hours=2)

        return {
            "access_token": self.access_token,
            "instance_url": self.connection.instance_url,
            "org_id": self.connection.org_id,
            "source": "simulated",
        }

    async def validate(self) -> bool:
        """Validate JWT token.

        Returns:
            True if token is valid
        """
        if not self.access_token:
            return False

        if not self.token_expiry:
            return False

        # Check if token expired (JWT tokens typically last 5 minutes)
        is_valid = datetime.now(UTC) < self.token_expiry

        if not is_valid:
            self.logger.warning("JWT token expired")

        return is_valid

    async def refresh(self) -> bool:
        """Refresh JWT token.

        Returns:
            True if refresh successful
        """
        self.logger.info("Refreshing JWT token")
        return await self.authenticate() is not None


class OAuth2Auth(SalesforceAuth):
    """OAuth2 authentication."""

    def __init__(self, connection: DeploymentConnection, refresh_token: str):
        """Initialize OAuth2 auth.

        Args:
            connection: DeploymentConnection
            refresh_token: Stored refresh token
        """
        super().__init__(connection)
        self.refresh_token = refresh_token

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate using OAuth2.

        Returns:
            Authentication details
        """
        self.logger.info(
            f"Authenticating with OAuth2 for org: {self.connection.org_id}"
        )

        # Simulate OAuth2 authentication when credentials flow is unavailable
        self.access_token = f"oauth_token_{self.connection.org_id}"
        self.token_expiry = datetime.now(UTC) + timedelta(hours=2)

        return {
            "access_token": self.access_token,
            "instance_url": self.connection.instance_url,
            "org_id": self.connection.org_id,
            "source": "simulated",
        }

    async def validate(self) -> bool:
        """Validate OAuth2 token.

        Returns:
            True if token is valid
        """
        if not self.access_token:
            return False

        # OAuth2 tokens typically last 2 hours
        is_valid = datetime.now(UTC) < self.token_expiry

        if not is_valid:
            self.logger.warning("OAuth2 token expired")

        return is_valid

    async def refresh(self) -> bool:
        """Refresh OAuth2 token using refresh token.

        Returns:
            True if refresh successful
        """
        self.logger.info("Refreshing OAuth2 token")

        if not self.refresh_token:
            return False

        return await self.authenticate() is not None


class SFDXAuth(SalesforceAuth):
    """Salesforce CLI (SFDX) authentication."""

    def __init__(
        self,
        connection: DeploymentConnection,
        cli_helper: SalesforceCliHelper | None = None,
    ) -> None:
        super().__init__(connection)
        self.cli_helper = cli_helper

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate using SFDX."""
        self.logger.info(
            f"Authenticating with SFDX for org: {self.connection.org_name}"
        )

        target_org = self.connection.org_name or self.connection.org_id
        if self.cli_helper is not None:
            org_info = await self.cli_helper.org_display(target_org)
            if org_info is not None:
                result_payload = org_info.get("result", org_info)
                if isinstance(result_payload, dict):
                    self.access_token = result_payload.get("accessToken", f"sfdx_token_{target_org}")
                    self.token_expiry = datetime.now(UTC) + timedelta(hours=2)
                    instance_url = result_payload.get("instanceUrl", self.connection.instance_url)
                    org_id = result_payload.get("id", self.connection.org_id)
                    return {
                        "access_token": self.access_token,
                        "instance_url": instance_url,
                        "org_id": org_id,
                        "source": "salesforce_cli",
                    }

        # Fallback when sf CLI is unavailable
        self.access_token = f"sfdx_token_{target_org}"
        self.token_expiry = datetime.now(UTC) + timedelta(hours=2)

        return {
            "access_token": self.access_token,
            "instance_url": self.connection.instance_url,
            "org_id": self.connection.org_id,
            "source": "simulated",
        }

    async def validate(self) -> bool:
        """Validate SFDX authentication.

        Returns:
            True if authenticated
        """
        # SFDX maintains persistent auth via .sfdx folder
        return self.access_token is not None

    async def refresh(self) -> bool:
        """Refresh SFDX authentication.

        Returns:
            True if refresh successful
        """
        self.logger.info("Refreshing SFDX authentication")
        return await self.authenticate() is not None


class UsernamePasswordAuth(SalesforceAuth):
    """Username and password authentication."""

    def __init__(
        self,
        connection: DeploymentConnection,
        username: str,
        password: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        security_token: Optional[str] = None,
    ):
        """Initialize username/password auth.

        Args:
            connection: DeploymentConnection
            username: Salesforce username
            password: Salesforce password
            client_id: OAuth Client ID
            client_secret: OAuth Client Secret
            security_token: User security token
        """
        super().__init__(connection)
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.security_token = security_token

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate using username and password via OAuth2 Password Grant.

        Returns:
            Authentication details
        """
        self.logger.info(f"Authenticating user: {self.username}")

        if not self.client_id or not self.client_secret or not self.password:
            self.logger.warning("OAuth credentials missing, falling back to simulation")
            self.access_token = f"simulated_token_{self.username}"
            self.token_expiry = datetime.now(UTC) + timedelta(hours=2)
            return {
                "access_token": self.access_token,
                "instance_url": self.connection.instance_url,
                "org_id": self.connection.org_id,
                "source": "simulated",
            }

        token_url = f"{self.connection.instance_url}/services/oauth2/token"
        # Security token must be appended to the password for the password grant flow
        password_payload = self.password + (self.security_token or "")

        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": password_payload,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(token_url, data=payload)
                response.raise_for_status()
                data = response.json()

                self.access_token = data["access_token"]
                self.token_expiry = datetime.now(UTC) + timedelta(hours=2)
                instance_url = data.get("instance_url", self.connection.instance_url)
                
                # Safely extract Org ID from the identity URL (usually at the end: .../id/orgId/userId)
                identity_url = data.get("id", "")
                org_id = self.connection.org_id
                if identity_url:
                    parts = identity_url.strip("/").split("/")
                    if len(parts) >= 2:
                        org_id = parts[-2]

                return {
                    "access_token": self.access_token,
                    "instance_url": instance_url,
                    "org_id": org_id,
                    "source": "oauth_password_grant",
                }
            except httpx.HTTPStatusError as e:
                error_msg = f"Salesforce OAuth failed: {e.response.text}"
                self.logger.error(error_msg)
                raise SalesforceAuthError(error_msg) from e
            except Exception as e:
                self.logger.error(f"Authentication error: {e}")
                raise SalesforceAuthError(f"Login failed: {str(e)}") from e

    async def validate(self) -> bool:
        """Validate authentication.

        Returns:
            True if authenticated
        """
        return self.access_token is not None

    async def refresh(self) -> bool:
        """Refresh authentication.

        Returns:
            True if refresh successful
        """
        self.logger.info("Refreshing username/password authentication")
        return await self.authenticate() is not None


class ConnectionManager:
    """Manages Salesforce connections."""

    def __init__(self, cli_helper: SalesforceCliHelper | None = None):
        """Initialize connection manager."""
        self.connections: Dict[str, SalesforceAuth] = {}
        self.cli_helper = cli_helper
        self.logger = logger

    async def create_connection(
        self,
        connection: DeploymentConnection,
        credentials: Optional[Dict[str, str]] = None,
    ) -> SalesforceAuth:
        """Create and authenticate a connection.

        Args:
            connection: DeploymentConnection configuration
            credentials: Optional credentials (username, password, refresh_token)

        Returns:
            SalesforceAuth instance

        Raises:
            SalesforceAuthError: If authentication fails
        """
        try:
            self.logger.info(f"Creating connection: {connection.org_name}")

            if connection.connection_type == ConnectionType.JWT:
                auth = JWTAuth(connection)
            elif connection.connection_type == ConnectionType.OAUTH2:
                refresh_token = (credentials or {}).get("refresh_token")
                if not refresh_token:
                    raise SalesforceAuthError("refresh_token required for OAuth2")
                auth = OAuth2Auth(connection, refresh_token)
            elif connection.connection_type == ConnectionType.SFDX:
                auth = SFDXAuth(connection, cli_helper=self.cli_helper)
            elif connection.connection_type == ConnectionType.USERNAME_PASSWORD:
                cfg = config_manager.settings.salesforce
                creds = credentials or {}
                
                username = creds.get("username") or cfg.username
                password = creds.get("password") or cfg.password
                security_token = creds.get("security_token") or cfg.security_token
                client_id = creds.get("client_id") or cfg.client_id
                client_secret = creds.get("client_secret") or cfg.client_secret
                
                auth = UsernamePasswordAuth(
                    connection,
                    username or "simulated_user",
                    password or "",
                    client_id=client_id,
                    client_secret=client_secret,
                    security_token=security_token,
                )
            else:
                raise SalesforceAuthError(
                    f"Unknown connection type: {connection.connection_type}"
                )

            # Authenticate
            await auth.authenticate()

            # Store connection
            self.connections[connection.id] = auth

            self.logger.info(f"Connection created: {connection.org_name}")

            return auth

        except Exception as e:
            self.logger.error(f"Connection creation failed: {e}")
            raise SalesforceAuthError(f"Connection failed: {e}") from e

    async def get_connection(self, connection_id: str) -> Optional[SalesforceAuth]:
        """Get a stored connection.

        Args:
            connection_id: Connection ID

        Returns:
            SalesforceAuth instance or None
        """
        auth = self.connections.get(connection_id)

        if auth and not await auth.validate():
            await auth.refresh()

        return auth

    async def close_connection(self, connection_id: str) -> bool:
        """Close a connection.

        Args:
            connection_id: Connection ID

        Returns:
            True if closed
        """
        if connection_id in self.connections:
            del self.connections[connection_id]
            self.logger.info(f"Connection closed: {connection_id}")
            return True

        return False

    async def close_all(self) -> None:
        """Close all connections."""
        self.connections.clear()
        self.logger.info("All connections closed")

    async def validate_connection(self, connection_id: str) -> bool:
        """Validate a connection is still valid.

        Args:
            connection_id: Connection ID

        Returns:
            True if connection is valid
        """
        auth = self.connections.get(connection_id)

        if not auth:
            return False

        return await auth.validate()
