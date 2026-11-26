"""CloudWatch metrics through Embedded Metric Format: one JSON log line, no extra API call.

Message text is never logged, only counters and timings.
"""

import json
import time

NAMESPACE = "CareerAssistant"


def emit(**values: int) -> None:
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": NAMESPACE,
                            "Dimensions": [[]],
                            "Metrics": [
                                {
                                    "Name": k,
                                    "Unit": "Milliseconds" if k.endswith("_ms") else "Count",
                                }
                                for k in values
                            ],
                        }
                    ],
                },
                **values,
            }
        ),
        flush=True,
    )
