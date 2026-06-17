#!/usr/bin/env python3
"""CDK app entry point for swelter's OPTIONAL serverless deployment.

This whole directory is optional. swelter runs on a single-board computer with no cloud at all
(see ../README.md, Mode 1). This stack only exists for collectives that want a hosted, public
copy of the dashboard behind a CDN. Committing it does not require anyone to deploy it.

Configuration is read from CDK context (set in cdk.json or passed with -c on the command line) so
nothing community-specific is baked into the code:

    cdk deploy -c budget_email=alerts@example.org -c monthly_budget_usd=5

Run from this directory with the AWS CDK Toolkit (npm i -g aws-cdk) and the Python deps in
requirements.txt installed.
"""

from __future__ import annotations

import aws_cdk as cdk

from swelter_serverless_stack import SwelterServerlessStack

app = cdk.App()

# The contact that should hear about a budget overrun, and the dollar ceiling. Defaults keep the
# bill in the single-digit range this project targets; override per deployment via -c.
budget_email = app.node.try_get_context("budget_email") or "REPLACE_ME@example.org"
monthly_budget_usd = float(app.node.try_get_context("monthly_budget_usd") or 5)

SwelterServerlessStack(
    app,
    "SwelterServerless",
    budget_email=budget_email,
    monthly_budget_usd=monthly_budget_usd,
    # Synthesize into the account/region your AWS credentials point at.
    env=cdk.Environment(
        account=None,  # picked up from the deploying credentials
        region=None,  # set CDK_DEFAULT_REGION or pass -c, or leave to the default profile
    ),
    description="OPTIONAL scale-to-zero copy of the swelter dashboard. Not required to run swelter.",
)

app.synth()
