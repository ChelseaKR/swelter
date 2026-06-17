"""The OPTIONAL swelter serverless stack.

Provisions, and nothing more:

  1. An S3 bucket + CloudFront distribution serving the static dashboard (web/).
  2. A scale-to-zero Lambda (function URL) serving swelter's READ-ONLY API.
  3. An AWS Budgets monthly cost alarm that emails a contact via SNS on overrun.

Design intent (mirrors ../README.md):
  - Nothing is always on. The dashboard is static files; the API function runs only while a
    request is in flight and otherwise costs nothing.
  - The data of record is NOT here. The authoritative store is the copyable folder on the host
    that runs swelter. This stack serves a published, read-only snapshot of it. If the whole
    account vanished, the observations would still exist in that folder.
  - Single-digit dollars a month is the target, so a hard budget alarm is part of the stack, not
    an afterthought a community group has to remember to set up.

Kept deliberately minimal and unexotic: only L2 constructs from aws-cdk-lib, no custom resources,
no third-party constructs. You should be able to read the whole thing in one sitting and delete it
with `cdk destroy` just as easily.
"""

from __future__ import annotations

from aws_cdk import (
    Aws,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct


class SwelterServerlessStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        budget_email: str,
        monthly_budget_usd: float,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- 1. Static dashboard: S3 (private) behind CloudFront ----------------------------
        #
        # The bucket is private; CloudFront reaches it through Origin Access Control, so the
        # dashboard is only ever served through the CDN, not from a public bucket. The web/ files
        # are static and have no server to crash — this is the part people actually look at and it
        # stays up on its own.
        site_bucket = s3.Bucket(
            self,
            "DashboardBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            # This bucket holds only a re-uploadable snapshot of web/, never the data of record,
            # so it is safe to empty and delete on `cdk destroy`. Nothing irreplaceable lives here.
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        distribution = cloudfront.Distribution(
            self,
            "DashboardCdn",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                # Open data, small payloads: cache aggressively at the edge to keep request costs
                # and origin reads low. Re-deploy invalidates by uploading fresh objects.
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            comment="swelter OPTIONAL static dashboard",
        )

        # Upload the committed dashboard (../../web) into the bucket on deploy. This is a snapshot:
        # regenerate web/sample-surface.json locally with `swelter demo` and redeploy to refresh.
        s3deploy.BucketDeployment(
            self,
            "DashboardContent",
            sources=[s3deploy.Source.asset("../../web")],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],  # invalidate the CDN cache so visitors see the new snapshot
        )

        # --- 2. Read-only API: a scale-to-zero Lambda with a function URL -------------------
        #
        # swelter's public API is GET-only by construction; there is no write path to expose. The
        # function runs only while a request is in flight and scales to zero between visitors, so a
        # quiet dashboard costs nothing. A cold start is slower, never an outage.
        #
        # The handler in lambda/handler.py is intentionally a thin, dependency-free stub: a real
        # deployment bundles the swelter package (and a read-only snapshot of the store) as the
        # function code or a layer. Kept out of this minimal stack so it stays readable; see the
        # cdk/README for how to package it.
        api_fn = lambda_.Function(
            self,
            "ReadOnlyApi",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda"),
            memory_size=256,  # small: the payloads are small and pre-aggregated
            timeout=Duration.seconds(15),
            description="swelter READ-ONLY API. Scales to zero between requests.",
        )

        api_url = api_fn.add_function_url(
            # Open data: no auth in front of a read-only endpoint. Put CloudFront in front later if
            # you want a single domain and edge caching for the API too.
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=["*"],  # open CORS, matching the stdlib server (open data)
                allowed_methods=[lambda_.HttpMethod.GET],
            ),
        )

        # --- 3. Budget alarm: a hard monthly cost ceiling with an SNS email -----------------
        #
        # A community group funds this. The failure mode that actually hurts is a surprise bill, so
        # the budget alarm is part of the stack. AWS Budgets publishes to an SNS topic when spend
        # crosses the thresholds below; the topic emails the contact. This watches the WHOLE
        # account's spend (Budgets is account-scoped), which is what you want for a funded copy.
        budget_topic = sns.Topic(self, "BudgetAlarmTopic", display_name="swelter budget alarm")
        budget_topic.add_subscription(subscriptions.EmailSubscription(budget_email))

        budgets.CfnBudget(
            self,
            "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=monthly_budget_usd,  # single-digit dollars: the stated target
                    unit="USD",
                ),
            ),
            notifications_with_subscribers=[
                # Warn early at 80% of forecast so there is time to react before the ceiling.
                _notify(budget_topic, comparison="GREATER_THAN", threshold=80, kind="FORECASTED"),
                # And again the moment actual spend crosses 100% of the ceiling.
                _notify(budget_topic, comparison="GREATER_THAN", threshold=100, kind="ACTUAL"),
            ],
        )

        # --- Outputs: where to point the dashboard / who to tell -----------------------------
        CfnOutput(self, "DashboardUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "ApiUrl", value=api_url.url)
        CfnOutput(self, "BudgetContact", value=budget_email)
        CfnOutput(self, "Account", value=Aws.ACCOUNT_ID)


def _notify(
    topic: sns.ITopic,
    *,
    comparison: str,
    threshold: float,
    kind: str,
) -> budgets.CfnBudget.NotificationWithSubscribersProperty:
    """One budget notification wired to the SNS topic. Factored out to keep the stack readable."""
    return budgets.CfnBudget.NotificationWithSubscribersProperty(
        notification=budgets.CfnBudget.NotificationProperty(
            comparison_operator=comparison,
            notification_type=kind,  # ACTUAL or FORECASTED
            threshold=threshold,
            threshold_type="PERCENTAGE",
        ),
        subscribers=[
            budgets.CfnBudget.SubscriberProperty(
                subscription_type="SNS",
                address=topic.topic_arn,
            )
        ],
    )
