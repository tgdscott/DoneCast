"""
Cloud Run domain mapping service for automated subdomain provisioning.

Handles automatic SSL certificate provisioning for podcast subdomains.
"""

import logging
import subprocess
import json
from typing import Optional

from api.core.config import settings


logger = logging.getLogger(__name__)

# Constants
PRIMARY_DOMAIN = "podcastplusplus.com"
GCP_REGION = "us-west1"
CLOUD_RUN_SERVICE = "podcast-web"


class DomainMappingError(Exception):
    """Raised when domain mapping operations fail."""
    pass


async def provision_subdomain(subdomain: str) -> dict:
    """
    Provision a Cloud Run domain mapping for a podcast subdomain.
    
    This creates a domain mapping that:
    1. Routes {subdomain}.podcastplusplus.com to podcast-web service
    2. Automatically provisions a FREE Google-managed SSL certificate
    3. Takes 10-15 minutes for SSL cert to become active
    
    Args:
        subdomain: The podcast subdomain (e.g., "cinema-irl")
        
    Returns:
        dict with status information:
        {
            "domain": "cinema-irl.podcastplusplus.com",
            "status": "pending" | "active" | "error",
            "ssl_status": "provisioning" | "active" | "error",
            "message": "descriptive message"
        }
        
    Raises:
        DomainMappingError: If the mapping cannot be created
    """
    domain = f"{subdomain}.{PRIMARY_DOMAIN}"
    
    try:
        result = subprocess.run(
            [
                "gcloud", "beta", "run", "domain-mappings", "create",
                f"--service={CLOUD_RUN_SERVICE}",
                f"--domain={domain}",
                f"--region={GCP_REGION}",
                "--quiet",  # Don't prompt
                "--format=json"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            
            # Check if domain mapping already exists
            if "already exists" in error_msg.lower():
                logger.info(f"Domain mapping already exists for {domain}")
                return {
                    "domain": domain,
                    "status": "active",
                    "ssl_status": "active",
                    "message": "Domain mapping already exists"
                }
            
            logger.error(f"Failed to create domain mapping for {domain}: {error_msg}")
            raise DomainMappingError(f"gcloud command failed: {error_msg}")
        
        logger.info(f"Successfully created domain mapping for {domain}")
        
        return {
            "domain": domain,
            "status": "pending",
            "ssl_status": "provisioning",
            "message": "Domain mapping created. SSL certificate will be ready in 10-15 minutes.",
            "dns_records": [
                {
                    "name": subdomain,
                    "type": "CNAME",
                    "value": "ghs.googlehosted.com."
                }
            ]
        }
        
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout creating domain mapping for {domain}")
        raise DomainMappingError("Domain mapping creation timed out")
        
    except Exception as e:
        logger.error(f"Unexpected error creating domain mapping for {domain}: {e}")
        raise DomainMappingError(f"Failed to create domain mapping: {str(e)}")


async def check_domain_status(subdomain: str) -> dict:
    """
    Check the status of a domain mapping and its SSL certificate.
    
    Args:
        subdomain: The podcast subdomain (e.g., "cinema-irl")
        
    Returns:
        dict with status information
    """
    domain = f"{subdomain}.{PRIMARY_DOMAIN}"
    
    try:
        result = subprocess.run(
            [
                "gcloud", "beta", "run", "domain-mappings", "describe",
                f"--domain={domain}",
                f"--region={GCP_REGION}",
                "--format=json"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {
                "domain": domain,
                "status": "not_found",
                "ssl_status": "not_found",
                "message": "Domain mapping does not exist"
            }
        
        import json
        data = json.loads(result.stdout)
        
        # Parse status conditions
        conditions = data.get("status", {}).get("conditions", [])
        cert_condition = next((c for c in conditions if c.get("type") == "CertificateProvisioned"), None)
        ready_condition = next((c for c in conditions if c.get("type") == "Ready"), None)
        
        ssl_status = "unknown"
        if cert_condition:
            if cert_condition.get("status") == "True":
                ssl_status = "active"
            elif cert_condition.get("status") == "Unknown":
                ssl_status = "provisioning"
            else:
                ssl_status = "error"
        
        overall_status = "unknown"
        if ready_condition:
            if ready_condition.get("status") == "True":
                overall_status = "active"
            elif ready_condition.get("status") == "Unknown":
                overall_status = "pending"
            else:
                overall_status = "error"
        
        return {
            "domain": domain,
            "status": overall_status,
            "ssl_status": ssl_status,
            "message": cert_condition.get("message", "") if cert_condition else "",
            "raw_conditions": conditions
        }
        
    except Exception as e:
        logger.error(f"Error checking domain status for {domain}: {e}")
        return {
            "domain": domain,
            "status": "error",
            "ssl_status": "error",
            "message": str(e)
        }


async def delete_domain_mapping(subdomain: str) -> bool:
    """
    Delete a domain mapping (for podcast deletion or subdomain change).
    
    Args:
        subdomain: The podcast subdomain to remove
        
    Returns:
        True if successful, False otherwise
    """
    domain = f"{subdomain}.{PRIMARY_DOMAIN}"
    
    try:
        result = subprocess.run(
            [
                "gcloud", "beta", "run", "domain-mappings", "delete",
                f"--domain={domain}",
                f"--region={GCP_REGION}",
                "--quiet"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully deleted domain mapping for {domain}")
            return True
        else:
            logger.error(f"Failed to delete domain mapping for {domain}: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting domain mapping for {domain}: {e}")
        return False
