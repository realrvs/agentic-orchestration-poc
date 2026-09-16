"""
Deploy BPMN process to Camunda 8 via Zeebe gRPC.

Usage:
    python deploy.py
"""

import asyncio
import os
import sys
from pathlib import Path

from pyzeebe import ZeebeClient
from pyzeebe.channel import create_insecure_channel


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")
BPMN_FILE = Path(__file__).parent.parent / "bpmn" / "process.bpmn"


async def main() -> None:
    if not BPMN_FILE.exists():
        print(f"ERROR: BPMN file not found: {BPMN_FILE}")
        sys.exit(1)

    print(f"Connecting to Zeebe at {CAMUNDA_ADDRESS}...")
    hostname, port = CAMUNDA_ADDRESS.split(":")
    channel = create_insecure_channel(hostname=hostname, port=int(port))
    client = ZeebeClient(channel)

    print(f"Deploying {BPMN_FILE.name}...")
    try:
        result = await client.deploy_resource(str(BPMN_FILE))
        print(f"Deployed successfully:")
        print(f"  {result}")
    except Exception as e:
        print(f"ERROR: Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())