from fastapi import HTTPException

from app.models.schemas import ConnectorType
from app.services.connectors.box import box_connector
from app.services.connectors.clio import clio_connector
from app.services.connectors.dropbox import dropbox_connector
from app.services.connectors.filevine import filevine_connector
from app.services.connectors.google_drive import google_drive_connector
from app.services.connectors.imanage import imanage_connector
from app.services.connectors.microsoft import microsoft_connector
from app.services.connectors.netdocuments import netdocuments_connector

# Registry of all connectors
CONNECTORS = {
    ConnectorType.GOOGLE_DRIVE: google_drive_connector,
    ConnectorType.ONEDRIVE: microsoft_connector,
    ConnectorType.BOX: box_connector,
    ConnectorType.DROPBOX: dropbox_connector,
    ConnectorType.NETDOCUMENTS: netdocuments_connector,
    ConnectorType.IMANAGE: imanage_connector,
    ConnectorType.FILEVINE: filevine_connector,
    ConnectorType.CLIO: clio_connector,
}


def get_connector(connector_type: ConnectorType):
    """Get a connector by type."""
    connector = CONNECTORS.get(connector_type)
    if not connector:
        raise HTTPException(
            status_code=400,
            detail=f"Connector type '{connector_type.value}' is not available. Available connectors: {', '.join(c.value for c in CONNECTORS)}",
        )
    return connector


async def get_all_connector_statuses(include_admin_only: bool = True):
    """Get status of all connectors.

    With ``include_admin_only=False`` a connector backed by a firm-wide
    credential (``requires_admin``) is reported as not connected without
    touching the provider, so a non-admin never opens a session with it.
    """
    statuses = []
    for connector_type, connector in CONNECTORS.items():
        if connector.requires_admin and not include_admin_only:
            statuses.append(
                {
                    "connected": False,
                    "configured": connector.is_configured,
                    "type": connector_type.value,
                    "admin_only": True,
                }
            )
            continue
        status = await connector.get_status()
        if connector.requires_admin:
            status["admin_only"] = True
        statuses.append(status)
    return statuses
