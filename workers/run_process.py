"""
Start a process instance for poc-procurement-process.

Usage:
    python run_process.py
"""

import asyncio
import os
import sys

from pyzeebe import ZeebeClient
from pyzeebe.channel import create_insecure_channel


CAMUNDA_ADDRESS = os.getenv("CAMUNDA_ZEEBE_GATEWAY_ADDRESS", "localhost:26500")
PROCESS_ID = "poc-procurement-process"


async def main() -> None:
    print(f"Connecting to Zeebe at {CAMUNDA_ADDRESS}...")
    hostname, port = CAMUNDA_ADDRESS.split(":")
    channel = create_insecure_channel(hostname=hostname, port=int(port))
    client = ZeebeClient(channel)

    variables = {
        "request_id": "REQ-001",
        "amount": 1500000,
        "comment": "Purchase of server hardware",
    }

    print(f"Starting process '{PROCESS_ID}' with variables:")
    for k, v in variables.items():
        print(f"  {k} = {v}")

    try:
        result = await client.run_process(
            bpmn_process_id=PROCESS_ID,
            variables=variables,
        )
        print(f"\nInstance started successfully:")
        print(f"  {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())